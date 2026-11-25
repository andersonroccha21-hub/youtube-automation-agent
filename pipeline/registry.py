from pipeline.models import STAGES
from skills.edicao import Edicao
from skills.imagens import Imagens
from skills.narracao import Narracao
from skills.pesquisa_titulos import PesquisaTitulos
from skills.plano_visual import PlanoVisual
from skills.roteiro import Roteiro
from skills.thumbnail import Thumbnail

SKILLS = {
    s.name: s
    for s in (
        PesquisaTitulos(),
        Thumbnail(),
        Roteiro(),
        PlanoVisual(),
        Narracao(),
        Imagens(),
        Edicao(),
    )
}
assert tuple(SKILLS) == STAGES
