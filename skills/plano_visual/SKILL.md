---
name: plano_visual
description: "Skill independente de produção YouTube: visual_plan.scenes."
---

# plano_visual

Cubra todas as seções com cenas. Use prompts visuais em inglês, IDs exatos das seções, termos de busca e pesos positivos para distribuição temporal. A duração real vem da narração posterior.

## Contrato

- Implementação: `skills.plano_visual.PlanoVisual`.
- Entrada: `pipeline.models.ScriptOutput`.
- Saída: `pipeline.models.VisualOutput`, preservando todos os campos anteriores.
- Novos dados: visual_plan.scenes.
- Artefatos: caminhos relativos à raiz da execução, com SHA-256.
- Configuração: exclusivamente pelo `Context.config` carregado do YAML do canal.
- Nunca incorpore nomes, públicos, vozes ou regras de um canal específico no código.

## Execução

O orquestrador registra esta skill em `pipeline/registry.py` e aplica as aprovações devidas. Para desenvolvimento isolado:

```bash
python main.py --channel channels/canal_exemplo/config.yaml \
  --skill plano_visual --input scratch/input.json \
  --output scratch/plano_visual.json --assets-dir scratch/artifacts
```

Os arquivos de entrada e artefatos precisam existir e respeitar o contrato. Acrescente `--demo` para fixtures sintéticas sem APIs pagas. Uma skill isolada não executa decisões humanas nem representa um pipeline aprovado. Use o fluxo normal do orquestrador para produção.

Os contratos exportados ficam em `schemas/plano_visual/`; regenere com `python scripts/export_schemas.py` após mudar os modelos.
