from __future__ import annotations
import atexit
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
import zipfile
from dataclasses import dataclass
from uuid import uuid4

from flask import Flask, jsonify, render_template, request, send_file, abort

from core import exporter
from core.caracteristicas import CARACTERISTICAS_COMBOBOX
from core.characteristics_utils import scan_feature, save_custom_mapping, get_custom_mappings
from core.subcategorias import get_custom_subcat, save_custom_subcat, get_subcategoria_options
from mappers import build_engine


@dataclass
class JobState:
    status: str  # "running" | "done" | "error"
    message: str = ""
    persons: int = 0
    properties: int = 0
    download_token: str | None = None


def _zip_directory(src_dir: str, zip_path: str) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(src_dir):
            for fname in files:
                abs_path = os.path.join(root, fname)
                arc_name = os.path.relpath(abs_path, src_dir)
                zf.write(abs_path, arc_name)


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024  # 512 MB

    upload_folder = tempfile.mkdtemp(prefix="msys_upload_")
    result_folder = tempfile.mkdtemp(prefix="msys_result_")
    atexit.register(shutil.rmtree, upload_folder, True)
    atexit.register(shutil.rmtree, result_folder, True)

    engine = build_engine()
    jobs: dict[str, JobState] = {}

    # ------------------------------------------------------------------ routes

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/systems")
    def get_systems():
        return jsonify({"systems": [m.NAME for m in engine.mappers]})

    @app.post("/api/export")
    def start_export():
        file = request.files.get("file")
        system = (request.form.get("system") or "").strip()
        password = request.form.get("password") or ""
        output_mode = request.form.get("output_mode") or "download"
        output_path = (request.form.get("output_path") or "").strip()
        imob_cpf_cnpj = re.sub(r"\D", "", request.form.get("imob_cpf_cnpj") or "")
        imob_nome = (request.form.get("imob_nome") or "").strip()

        if not file or not file.filename:
            return jsonify({"error": "Nenhum arquivo enviado."}), 400
        if not system:
            return jsonify({"error": "Sistema não selecionado."}), 400
        if output_mode == "path" and not output_path:
            return jsonify({"error": "Caminho de saída obrigatório."}), 400

        # Preserve original extension
        original_name = file.filename
        ext = os.path.splitext(original_name)[1].lower()
        upload_path = os.path.join(upload_folder, f"{uuid4().hex}{ext}")
        file.save(upload_path)

        job_id = str(uuid4())
        jobs[job_id] = JobState(status="running")

        # Trim jobs dict if it grows too large
        if len(jobs) > 100:
            oldest = list(jobs.keys())[:50]
            for k in oldest:
                jobs.pop(k, None)

        context = {"imob_cpf_cnpj": imob_cpf_cnpj, "imob_nome": imob_nome}
        threading.Thread(
            target=_run_job,
            args=(jobs, engine, upload_path, job_id, system, password,
                  output_mode, output_path, result_folder, context),
            daemon=True,
        ).start()

        return jsonify({"job_id": job_id})

    @app.get("/api/job/<job_id>")
    def get_job(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            return jsonify({"error": "Job não encontrado."}), 404

        resp: dict = {
            "status": job.status,
            "message": job.message,
            "persons": job.persons,
            "properties": job.properties,
            "download_url": (
                f"/api/download/{job.download_token}"
                if job.download_token else None
            ),
        }
        return jsonify(resp)

    @app.post("/api/scan")
    def scan_chars():
        file = request.files.get("file")
        system = (request.form.get("system") or "").strip()
        password = request.form.get("password") or ""

        if not file or not file.filename:
            return jsonify({"error": "Nenhum arquivo enviado."}), 400
        if not system:
            return jsonify({"error": "Sistema não selecionado."}), 400

        mapper = engine.get_mapper(system)
        if mapper is None:
            return jsonify({"error": f"Sistema '{system}' não reconhecido."}), 400

        original_name = file.filename
        ext = os.path.splitext(original_name)[1].lower()
        upload_path = os.path.join(upload_folder, f"{uuid4().hex}{ext}")
        file.save(upload_path)

        try:
            is_zip = upload_path.lower().endswith(".zip")
            if is_zip:
                data = engine.load_zip(upload_path, password)
            else:
                data = engine.load_file(upload_path)

            raw_names: set[str] = mapper.scan_characteristics(data)
            raw_subcats: set[str] = mapper.scan_subcategories(data)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
        finally:
            try:
                os.remove(upload_path)
            except OSError:
                pass

        uncertain: list[dict] = []
        unmatched: list[dict] = []
        for name in sorted(raw_names):
            info = scan_feature(name)
            if info["status"] == "uncertain":
                uncertain.append({"source": name, "suggested": info["suggested"], "score": info["score"]})
            elif info["status"] in ("unmatched", "ignored"):
                # "ignored" = blocklist; exibido com "Ignorar sempre" pré-selecionado
                pre_ignore = info["status"] == "ignored"
                unmatched.append({"source": name, "pre_ignore": pre_ignore})

        # Subcategorias sem mapeamento (nem em _SUB, nem em custom)
        subcats: list[dict] = []
        for src in sorted(raw_subcats):
            tipo, _, subtipo = src.partition("|")
            if get_custom_subcat(tipo, subtipo) is None:
                subcats.append({"source": src})

        canonicals = sorted(CARACTERISTICAS_COMBOBOX.values())
        return jsonify({
            "uncertain": uncertain,
            "unmatched": unmatched,
            "subcats": subcats,
            "subcat_options": get_subcategoria_options(),
            "has_issues": bool(uncertain or unmatched or subcats),
            "canonicals": canonicals,
        })

    @app.get("/api/mappings/caracteristicas")
    def get_char_mappings():
        return jsonify(get_custom_mappings())

    @app.post("/api/mappings/caracteristicas")
    def save_char_mappings():
        body = request.get_json(force=True, silent=True) or {}
        mappings: list[dict] = body.get("mappings", [])
        for item in mappings:
            source = item.get("source")
            canonical = item.get("canonical")  # str or None
            if source:
                save_custom_mapping(source, canonical if canonical else None)
        return jsonify({"ok": True})

    @app.get("/api/mappings/subcategorias")
    def get_subcat_mappings():
        from core.subcategorias import _custom_subs
        return jsonify(_custom_subs)

    @app.post("/api/mappings/subcategorias")
    def save_subcat_mappings():
        body = request.get_json(force=True, silent=True) or {}
        mappings: list[dict] = body.get("mappings", [])
        for item in mappings:
            source = item.get("source", "")
            id_str = item.get("id") or None
            if source:
                tipo, _, subtipo = source.partition("|")
                save_custom_subcat(tipo, subtipo, id_str)
        return jsonify({"ok": True})

    @app.get("/api/open-folder")
    def open_folder():
        path = (request.args.get("path") or "").strip()
        path = os.path.normpath(path)
        if not path or not os.path.isdir(path):
            return jsonify({"error": "Pasta não encontrada."}), 400
        try:
            subprocess.Popen(["explorer", path])
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/browse-folder")
    def browse_folder():
        initial = (request.args.get("initial") or "").strip()
        if not initial or not os.path.isdir(initial):
            initial = os.path.expanduser("~")
        script = (
            "import tkinter as tk; from tkinter import filedialog; "
            "root = tk.Tk(); root.withdraw(); root.wm_attributes('-topmost', True); "
            f"p = filedialog.askdirectory(title='Selecionar pasta de sa\u00edda', initialdir={repr(initial)}); "
            "print(p or '', end='')"
        )
        try:
            proc = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                timeout=120,
            )
            path = os.path.normpath(proc.stdout.strip()) if proc.stdout.strip() else ""
        except Exception:
            path = ""
        return jsonify({"path": path})

    @app.get("/api/download/<token>")
    def download_result(token: str):
        if not re.fullmatch(r"[0-9a-f]{32}", token):
            abort(400)
        zip_path = os.path.join(result_folder, f"{token}.zip")
        if not os.path.exists(zip_path):
            abort(404)

        response = send_file(
            zip_path,
            as_attachment=True,
            download_name="exportacao_msys.zip",
            mimetype="application/zip",
        )

        @response.call_on_close
        def _cleanup():
            try:
                os.remove(zip_path)
            except OSError:
                pass

        return response

    return app


# ------------------------------------------------------------------ background worker

def _run_job(
    jobs: dict,
    engine,
    upload_path: str,
    job_id: str,
    system: str,
    password: str,
    output_mode: str,
    output_path: str,
    result_folder: str,
    context: dict | None = None,
) -> None:
    try:
        is_zip = upload_path.lower().endswith(".zip")
        if is_zip:
            result = engine.run_zip(system, upload_path, password, context=context)
        else:
            result = engine.run(system, upload_path, context=context)

        if output_mode == "path":
            out_dir = output_path
            os.makedirs(out_dir, exist_ok=True)
        else:
            out_dir = os.path.join(result_folder, job_id)
            os.makedirs(out_dir, exist_ok=True)

        exporter.export(result, out_dir)

        n_persons = len(result.persons)
        n_props = (
            len(result.property_result.properties)
            if result.property_result else 0
        )

        if output_mode == "download":
            token = uuid4().hex
            zip_path = os.path.join(result_folder, f"{token}.zip")
            _zip_directory(out_dir, zip_path)
            shutil.rmtree(out_dir, ignore_errors=True)

            props_txt = f", {n_props} imóvel(is)" if n_props else ""
            jobs[job_id] = JobState(
                status="done",
                message=f"{n_persons} pessoa(s){props_txt} exportada(s).",
                persons=n_persons,
                properties=n_props,
                download_token=token,
            )
        else:
            props_txt = f", {n_props} imóvel(is)" if n_props else ""
            jobs[job_id] = JobState(
                status="done",
                message=f"{n_persons} pessoa(s){props_txt} → {output_path}",
                persons=n_persons,
                properties=n_props,
            )

    except Exception:
        jobs[job_id] = JobState(
            status="error",
            message=traceback.format_exc(),
        )
    finally:
        try:
            os.remove(upload_path)
        except OSError:
            pass
