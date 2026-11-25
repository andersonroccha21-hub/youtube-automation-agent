---
name: pesquisa_titulos
description: "Skill independente de produção YouTube: research.summary, research.sources e research.candidates."
---

# pesquisa_titulos

Pesquise o nicho usando fontes fornecidas ou pesquisa YouTube, gere títulos originais e justifique os ângulos. A seleção é exclusivamente humana. Não preencha research.selected_id.

## Contrato

- Implementação: `skills.pesquisa_titulos.PesquisaTitulos`.
- Entrada: `pipeline.models.Brief`.
- Saída: `pipeline.models.ResearchOutput`, preservando todos os campos anteriores.
- Novos dados: research.summary, research.sources e research.candidates.
- Artefatos: caminhos relativos à raiz da execução, com SHA-256.
- Configuração: exclusivamente pelo `Context.config` carregado do YAML do canal.
- Nunca incorpore nomes, públicos, vozes ou regras de um canal específico no código.

## Execução

O orquestrador registra esta skill em `pipeline/registry.py` e aplica as aprovações devidas. Para desenvolvimento isolado:

```bash
python main.py --channel channels/canal_exemplo/config.yaml \
  --skill pesquisa_titulos --input scratch/input.json \
  --output scratch/pesquisa_titulos.json --assets-dir scratch/artifacts
```

Os arquivos de entrada e artefatos precisam existir e respeitar o contrato. Acrescente `--demo` para fixtures sintéticas sem APIs pagas. Uma skill isolada não executa decisões humanas nem representa um pipeline aprovado. Use o fluxo normal do orquestrador para produção.

Os contratos exportados ficam em `schemas/pesquisa_titulos/`; regenere com `python scripts/export_schemas.py` após mudar os modelos.
