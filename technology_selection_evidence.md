# Technology Selection — Evidence Log (source log)

> 이 문서는 `agent_discovery_recommendation_implementation.md` §4 후보 판정의 **근거 로그**다. 본문에는 citation을 싣지 않고, 강한 disqualifier(archived / non-commercial / broken / EOL)와 버전·유지보수 판정의 출처·확인일을 여기에 남긴다. 추후 별도 `technology_selection` 문서로 본격 정리할 때 이 표를 옮긴다.
>
> **검증 방법**: 독립 web 리서치(4개 영역 — entity linking / KG access / KG embedding·vector / recommendation·eval), 1차 소스(공식 repo/PyPI/arXiv/벤더 문서) 우선. **확인일: 2026-06-22.** 버전·날짜는 그 시점 기준이며 변동될 수 있으니 재확인 후 갱신한다.

## 1. Entity linking (§4.1)

| 항목 | 판정 | 핵심 근거 (확인일 2026-06-22) | source |
|---|---|---|---|
| ReFinED (Amazon) | reference (영어 전용) | native Wikidata QID·zero-shot이나 **English-only**, repo 2022 이후 dormant. AIDA ~90.2 F1 | arXiv:2207.04108 · github.com/amazon-science/ReFinED |
| OpenTapioca | drop | **인명/지명 NEL only**(topical 아님), 한국어 없음, AIDA micro-F1 ~0.48, demo down, v0.1.0(2019) 이후 정지 | arXiv:1904.09131 · snyk.io/advisor/python/opentapioca |
| ReLiK (Sapienza) | drop (commercial 차단) | **CC-BY-NC-SA 4.0**, English-only, **Wikipedia 링크(QID 아님)**, ACL2024 Findings, v1.0.7(2024-09) | arXiv:2408.00103 · huggingface.co/sapienzanlp/relik-entity-linking-large |
| BELA (Meta) | reference | 97개 언어(ko 포함)·MIT지만 **repo archived 2025-11-01**, serving path 없음, **한국어 벤치 없음** | arXiv:2306.08896 · github.com/facebookresearch/BELA |
| BLINK (Meta) | reference | **archived 2024-03**, English-only, Wikipedia(QID 아님), MIT | github.com/facebookresearch/BLINK |
| GENRE / mGENRE (Meta) | reference (commercial 차단) | **archived(GENRE 2025-07)**, **CC-BY-NC 4.0**, mGENRE만 ko 학습·QID 근접(매핑 필요), heavy trie beam-search | TACL2022 · huggingface.co/facebook/mgenre-wiki |
| LLM rerank/disambiguation | keep-with-caveat | retriever 후보 위 rerank만. **LLM 단독 QID 콜드 생성은 hallucination 위험**(보고된 정밀도 매우 낮음) → gold set 검증 전 금지 | arXiv:2407.04020 (LLMAEL) · arXiv:2305.14202 |

**종합**: 한국어 topic→QID **turnkey 오픈모델 없음** → candidate generator(Wikidata label/alias + dense retrieval + memory-api anchor search) + LLM rerank **2-tier**. ReFinED·BELA·mGENRE는 아키텍처 레퍼런스.

## 2. Wikidata / KG access (§4.1)

| 항목 | 판정 | 핵심 근거 (확인일 2026-06-22) | source |
|---|---|---|---|
| WDQS (public SPARQL) | keep-with-caveat | **2025-05 graph split**(scholarly 분리), rate limit(~5 parallel/IP, 429) → production hot path 부적합 | wikidata.org/wiki/Wikidata:SPARQL_query_service/WDQS_graph_split · wikitech.wikimedia.org/wiki/Wikidata_Query_Service/Technical_interactions |
| Wikidata dumps | keep | CC0, self-host/offline index의 정본 입력 | wikidata.org/wiki/Wikidata:Tools/For_programmers |
| qwikidata | recharacterize | dump-parser/thin client, v0.4.2(~2019) 이후 미유지보수 — 엔진 아님 | qwikidata.readthedocs.io · github.com/kensho-technologies/qwikidata |
| **QLever** (Uni Freiburg) | keep (self-host 1순위) | full Wikidata 단일 장비 수용(>1T triples), SPARQL 1.1 완전(2025-06), **Wikimedia가 택한 WDQS 차기 백엔드** | github.com/ad-freiburg/qlever · wikidata.org/wiki/Wikidata:SPARQL_query_service/WDQS_backend_update |
| Oxigraph | keep-with-caveat | 활발(v0.5.x, 2026), 그러나 **full Wikidata 로드 >1주**·plan optimizer 약함 → subset/sparse fallback 한정 | github.com/oxigraph/oxigraph · thomas.pellissier-tanon.fr/blog/2023-01-15-wdqs.html |
| Blazegraph | **drop / EOL** | ~2018 개발 중단(Amazon이 개발자 흡수→Neptune), ~2020 이후 unmaintained, **WDQS가 떠나는 중인 legacy** | en.wikipedia.org/wiki/Blazegraph · docs.aws.amazon.com/neptune/latest/userguide/migrating-from-blazegraph.html |

## 3. KG embedding (§4.1)

| 항목 | 판정 | 핵심 근거 (확인일 2026-06-22) | source |
|---|---|---|---|
| PyKEEN | keep-with-caveat | 활발(v1.11.x, 2025), MIT, **단일 GPU only**(분산 없음) → 실험·재현성 | pypi.org/project/pykeen · github.com/pykeen/pykeen issue #96 |
| DGL-KE (AWS) | drop/정정 | v0.1.2(2021), 마지막 실질 commit 2023-03, **최신 DGL(≥0.8)에서 broken**, README가 **GraphStorm으로 redirect** | pypi.org/pypi/dglke/json · github.com/awslabs/dgl-ke |
| GraphStorm (대체) | keep (대규모) | DGL-KE의 유지보수 후속, 대규모 GML(분산 KGE 포함) | github.com/awslabs/graphstorm (본격 검증은 technology_selection에서) |
| AmpliGraph | drop | v2.1.0(2024-02) 이후 dormant, tf==2.9 핀, YAGO3-10급 스케일(Wikidata 부적합) | pypi.org/project/ampligraph · docs.ampligraph.org |
| PyTorch-BigGraph (Meta) | reference | **archived 2024-03**(read-only), 그러나 **Wikidata 78M 엔티티 임베딩 다운로드 가능** → frozen reference | github.com/facebookresearch/PyTorch-BigGraph · arXiv:1903.12287 |

## 4. ANN / vector (§4.1) — 5종 모두 2026 활발·permissive

| 항목 | 역할 | 핵심 근거 (확인일 2026-06-22) | source |
|---|---|---|---|
| pgvector | Postgres 내 시작 | v0.8.x(2026), **0.8+ iterative scan으로 filtered ANN 수천만**; 한계는 단일 노드 스케일 | github.com/pgvector/pgvector CHANGELOG · AWS Aurora pgvector 0.8.0 blog |
| Qdrant | 가벼운 first-reach 독립 DB | v1.18.x(2026), Apache-2.0, **filter-aware HNSW** | github.com/qdrant/qdrant · qdrant.tech/articles/vector-search-filtering |
| Milvus | 무거운 scale-out | v2.6.x(2026), Apache-2.0, 분산(etcd+object store+MQ) — graduate-to | github.com/milvus-io/milvus · milvus.io/docs/filtered-search.md |
| Faiss (Meta) | 라이브러리 | v1.14.x(2026), MIT, **네이티브 메타데이터 필터 없음**(IDSelector 직접) | github.com/facebookresearch/faiss CHANGELOG |
| Vespa | retrieve+filter+rank 통합 | 8.x(2026, 주간 릴리스), Apache-2.0, 무거운 클러스터 | github.com/vespa-engine/vespa · docs.vespa.ai/en/ranking.html |

## 5. Recommendation / ranking / eval (§4.2)

| 항목 | 판정 | 핵심 근거 (확인일 2026-06-22) | source |
|---|---|---|---|
| LightGBM | keep-with-caveat | v4.6.0(2025-02, 태그 stale), **repo가 `microsoft/`→`lightgbm-org/`로 이전(2026-03)** — 핀/URL 갱신 | github.com/lightgbm-org/LightGBM |
| XGBoost (rank:ndcg) | keep | v3.3.0(2026-06), Apache-2.0 | github.com/dmlc/xgboost |
| CatBoost ranking | keep | v1.2.10(2026-02), Apache-2.0 | github.com/catboost/catboost |
| RecBole | keep (benchmark) | v1.2.1(2024-02), MIT — research benchmark | github.com/RUCAIBox/RecBole |
| TFRS | **drop/recharacterize** | v0.7.7(2025-01, version bump only), **Keras 2 legacy 동결**; Google이 `keras-rs`로 이동 | github.com/tensorflow/recommenders · keras.io/keras_rs |
| keras-rs | research candidate | Keras 3 multi-backend(TF/JAX/PyTorch) — production 단정 이르름 | github.com/keras-team/keras-rs |
| TorchRec (Meta) | keep | v1.6.0(2026-03), BSD-3, 분기 릴리스 | github.com/pytorch/torchrec |
| Merlin (NVIDIA) | keep-with-caveat | suite v24.06(2024) 이후 정체 → GPU preprocessing 한정 | github.com/NVIDIA-Merlin/Merlin |
| Evidently | keep (드리프트) | v0.7.x(2026-03), Apache-2.0 — ranking metric/OPE 아님 | github.com/evidentlyai/evidently |
| OBP (off-policy) | keep-with-caveat | 원본 `st-tech/zr-obp` **2022 이후 dormant** → fork `sb-ai-lab/sb-obp`(sb-obp 0.5.10, 2025-08) 또는 reference-only | github.com/st-tech/zr-obp · github.com/sb-ai-lab/sb-obp |
| IR metric 구현 | keep | 유지보수 구현 사용: TorchMetrics(1.9.0)·ranx(0.3.21)·`pytrec-eval-terrier`(2025-10). 구형 `pytrec_eval`(2020) 회피 | github.com/Lightning-AI/torchmetrics · github.com/AmenRa/ranx |

## 6. NLP primitives — stance/topic (§4.3)

| 항목 | 판정 | 핵심 근거 (확인일 2026-06-22) | source |
|---|---|---|---|
| PyABSA | keep-with-caveat | v2.4.3(2025-08), MIT, **single-maintainer bus-factor** | github.com/yangheng95/PyABSA |
| InstructABSA | reference-only | NAACL-2024 논문 코드, 릴리스/PyPI 없음 | github.com/kevinscaria/InstructABSA |
| ABSA(일반) | primitive only | cross-lingual TASD F1 ~16–34%(2025) — domain transfer 약함 | (서베이, technology_selection에서 보강) |
| BERTopic | keep | v0.17.x(2025-07), MIT | github.com/MaartenGr/BERTopic |
| PyMC | keep | v6.0.x(2026-05), Apache-2.0 — ideal-point | github.com/pymc-devs/pymc |
| Stan / CmdStan | keep | v2.37.0(2025-09), BSD-3 | github.com/stan-dev/cmdstan |
