---
name: roteiro
description: "Skill independente de produção YouTube: script.title e script.sections."
---

# roteiro

Exija título e thumbnail selecionados. Escreva o roteiro completo em seções, no idioma e tom do canal, preservando o título e os IDs das fontes. Narração de até 3500 caracteres por seção.

## Contrato

- Implementação: `skills.roteiro.Roteiro`.
- Entrada: `pipeline.models.ThumbnailOutput`.
- Saída: `pipeline.models.ScriptOutput`, preservando todos os campos anteriores.
- Novos dados: script.title e script.sections.
- Artefatos: caminhos relativos à raiz da execução, com SHA-256.
- Configuração: exclusivamente pelo `Context.config` carregado do YAML do canal.
- Nunca incorpore nomes, públicos, vozes ou regras de um canal específico no código.

## Execução

O orquestrador registra esta skill em `pipeline/registry.py` e aplica as aprovações devidas. Para desenvolvimento isolado:

```bash
python main.py --channel channels/canal_exemplo/config.yaml \
  --skill roteiro --input scratch/input.json \
  --output scratch/roteiro.json --assets-dir scratch/artifacts
```

Os arquivos de entrada e artefatos precisam existir e respeitar o contrato. Acrescente `--demo` para fixtures sintéticas sem APIs pagas. Uma skill isolada não executa decisões humanas nem representa um pipeline aprovado. Use o fluxo normal do orquestrador para produção.

Os contratos exportados ficam em `schemas/roteiro/`; regenere com `python scripts/export_schemas.py` após mudar os modelos.
