from __future__ import annotations
import os
import threading
import traceback

try:
    import customtkinter as ctk
    _USE_CTK = True
except ImportError:
    import tkinter as ctk  # type: ignore
    from tkinter import ttk  # type: ignore
    _USE_CTK = False

from tkinter import filedialog, messagebox

VERSION = "v4.6"
TITLE = f"MSYS Importação de Dados {VERSION}"


class App:
    def __init__(self):
        if _USE_CTK:
            ctk.set_appearance_mode("System")
            ctk.set_default_color_theme("blue")
            self.root = ctk.CTk()
        else:
            import tkinter as tk
            self.root = tk.Tk()

        self.root.title(TITLE)
        self.root.resizable(False, False)

        self._file_path = ""
        self._output_dir = ""
        self._engine = None
        self._mapper_names: list[str] = []

        self._build_ui()
        self._load_engine()

    def _load_engine(self):
        try:
            from mappers import build_engine
            self._engine = build_engine()
            self._mapper_names = [m.NAME for m in self._engine.mappers]
            self._update_combobox()
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao carregar mappers:\n{e}")

    def _build_ui(self):
        pad = {"padx": 12, "pady": 6}

        self._make_label("Arquivo de origem:").grid(row=0, column=0, sticky="w", **pad)
        self._file_var = self._make_string_var()
        self._file_entry = self._make_entry(textvariable=self._file_var, width=400, state="readonly")
        self._file_entry.grid(row=0, column=1, **pad)
        self._make_button("Selecionar", self._browse_file).grid(row=0, column=2, **pad)

        self._make_label("Sistema:").grid(row=1, column=0, sticky="w", **pad)
        self._system_var = self._make_string_var()
        self._combo = self._make_combobox(textvariable=self._system_var, width=300, state="readonly")
        self._combo.grid(row=1, column=1, sticky="w", **pad)

        self._pwd_label = self._make_label("Senha ZIP:")
        self._pwd_label.grid(row=2, column=0, sticky="w", **pad)
        self._pwd_var = self._make_string_var()
        self._pwd_entry = self._make_entry(textvariable=self._pwd_var, width=200, show="*")
        self._pwd_entry.grid(row=2, column=1, sticky="w", **pad)
        self._pwd_label.grid_remove()
        self._pwd_entry.grid_remove()

        self._make_label("Pasta de saída:").grid(row=3, column=0, sticky="w", **pad)
        self._out_var = self._make_string_var()
        self._out_entry = self._make_entry(textvariable=self._out_var, width=400)
        self._out_entry.grid(row=3, column=1, **pad)
        self._make_button("Selecionar", self._browse_output).grid(row=3, column=2, **pad)

        self._export_btn = self._make_button("Exportar", self._on_export)
        self._export_btn.grid(row=4, column=1, pady=16)

        self._status_var = self._make_string_var(value="Pronto.")
        self._status_label = self._make_label(textvariable=self._status_var)
        self._status_label.grid(row=5, column=0, columnspan=3, **pad)

        self.root.columnconfigure(1, weight=1)

    # -- helpers UI --

    def _make_label(self, text: str = "", **kw):
        if _USE_CTK:
            return ctk.CTkLabel(self.root, text=text, **kw)
        import tkinter as tk
        return tk.Label(self.root, text=text, **kw)

    def _make_entry(self, **kw):
        if _USE_CTK:
            return ctk.CTkEntry(self.root, **kw)
        import tkinter as tk
        return tk.Entry(self.root, **kw)

    def _make_button(self, text: str, command=None):
        if _USE_CTK:
            return ctk.CTkButton(self.root, text=text, command=command)
        import tkinter as tk
        return tk.Button(self.root, text=text, command=command)

    def _make_combobox(self, **kw):
        if _USE_CTK:
            return ctk.CTkComboBox(self.root, **kw)
        import tkinter as tk
        from tkinter import ttk
        values = kw.pop("values", [])
        cb = ttk.Combobox(self.root, **kw)
        cb["values"] = values
        return cb

    def _make_string_var(self, value: str = ""):
        import tkinter as tk
        return tk.StringVar(value=value)

    def _update_combobox(self):
        if _USE_CTK:
            self._combo.configure(values=self._mapper_names)
        else:
            self._combo["values"] = self._mapper_names

    # -- actions --

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Selecionar arquivo",
            filetypes=[
                ("Todos os suportados", "*.xml *.xlsx *.xls *.zip *.sql *.json"),
                ("XML", "*.xml"),
                ("Excel", "*.xlsx *.xls"),
                ("ZIP", "*.zip"),
                ("SQL", "*.sql"),
                ("JSON", "*.json"),
                ("Todos", "*.*"),
            ],
        )
        if not path:
            return
        self._file_path = path
        self._file_var.set(path)
        # Auto-preenche pasta de saída
        if not self._out_var.get():
            self._out_var.set(os.path.dirname(path))

        # Mostra campo de senha se for ZIP
        is_zip = path.lower().endswith(".zip")
        if is_zip:
            self._pwd_label.grid()
            self._pwd_entry.grid()
        else:
            self._pwd_label.grid_remove()
            self._pwd_entry.grid_remove()

    def _browse_output(self):
        path = filedialog.askdirectory(title="Selecionar pasta de saída")
        if path:
            self._out_var.set(path)

    def _on_export(self):
        file_path = self._file_var.get()
        system = self._system_var.get()
        output_dir = self._out_var.get()

        if not file_path:
            messagebox.showwarning("Atenção", "Selecione um arquivo de origem.")
            return
        if not system:
            messagebox.showwarning("Atenção", "Selecione o sistema.")
            return
        if not output_dir:
            messagebox.showwarning("Atenção", "Selecione a pasta de saída.")
            return

        self._export_btn.configure(state="disabled") if _USE_CTK else self._export_btn.config(state="disabled")
        self._status_var.set("Exportando...")

        password = self._pwd_var.get()
        threading.Thread(
            target=self._run_export,
            args=(file_path, system, output_dir, password),
            daemon=True,
        ).start()

    def _run_export(self, file_path: str, system: str, output_dir: str, password: str):
        try:
            from core import exporter
            is_zip = file_path.lower().endswith(".zip")
            if is_zip:
                result = self._engine.run_zip(system, file_path, password)
            else:
                result = self._engine.run(system, file_path)

            exporter.export(result, output_dir)

            n_persons = len(result.persons)
            n_props = len(result.property_result.properties) if result.property_result else 0
            msg = f"Exportação concluída! {n_persons} pessoa(s)"
            if n_props:
                msg += f", {n_props} imóvel(is)"
            msg += f" → {output_dir}"
            self.root.after(0, lambda: self._on_done(msg, success=True))
        except Exception:
            err = traceback.format_exc()
            self.root.after(0, lambda: self._on_done(f"Erro:\n{err}", success=False))

    def _on_done(self, msg: str, success: bool):
        self._export_btn.configure(state="normal") if _USE_CTK else self._export_btn.config(state="normal")
        self._status_var.set(msg[:120])
        if success:
            messagebox.showinfo("Concluído", msg)
        else:
            messagebox.showerror("Erro na exportação", msg)

    def run(self):
        self.root.mainloop()
