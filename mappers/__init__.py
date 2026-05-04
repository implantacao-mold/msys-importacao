from core.engine import ExportEngine
from mappers.arbo import ArboMapper
from mappers.code49 import Code49Mapper
from mappers.imobzi import ImobziMapper
from mappers.imobi_brasil import ImobiBrasilMapper
from mappers.jetimob import JetImobMapper
from mappers.kenlo import KenloMapper
from mappers.msys_imob import MsysImobMapper
from mappers.tec_imob import TecImobMapper
from mappers.univen import UnivenMapper
from mappers.vista import VistaMapper


def build_engine() -> ExportEngine:
    engine = ExportEngine()
    for mapper_cls in sorted(
        [
            ArboMapper,
            Code49Mapper,
            ImobiBrasilMapper,
            ImobziMapper,
            JetImobMapper,
            KenloMapper,
            MsysImobMapper,
            TecImobMapper,
            UnivenMapper,
            VistaMapper,
        ],
        key=lambda c: c.NAME,
    ):
        engine.register(mapper_cls())
    return engine
