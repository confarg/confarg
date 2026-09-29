# Plain dicts between stages

See [pipeline](../pipeline/stages.md#plain-dicts-as-the-intermediate-representation).
Precedents: pydantic-settings and Dynaconf merge mappings before validation; OmegaConf keeps its
own `DictConfig` container. A *plain* dict keeps confarg dependency-free and decomposable.
