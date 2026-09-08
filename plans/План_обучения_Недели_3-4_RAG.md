НЕДЕЛЯ 3: Embeddings и чанкинг

День 15 — Теория эмбеддингов (~2 ч)
Источники:
Vector Embeddings Explained (Redis Blog): https://redis.io/blog/vector-embeddings-explained/
A Beginner's Guide to Vector Embeddings (TigerData): https://www.tigerdata.com/blog/a-beginners-guide-to-vector-embeddings
Что сделать:
Прочитать оба материала: от one-hot encoding к плотным векторам, метрики расстояния (евклидово, косинусное, скалярное произведение)
Выписать в конспект: что такое размерность вектора (768/1536/3072), почему семантически близкие тексты дают близкие векторы
Руками в Python: взять 2 трёхмерных вектора, посчитать косинусное сходство по формуле (numpy, без библиотек)
Придумать 3 пары фраз: близкие по смыслу / разные по смыслу / похожие по словам, но разные по смыслу («банк реки» / «банк денег»)
Контрольная точка: можете вслух объяснить, что такое эмбеддинг и косинусное сходство, без слов «нейросеть как-то там кодирует».

День 16 — Эмбеддинги через API и локально (~2 ч)
Источники:
OpenAI Embeddings guide: https://platform.openai.com/docs/guides/embeddings
Sentence Transformers Quickstart: https://www.sbert.net/docs/quickstart.html
Что сделать:
Получить эмбеддинг фразы через OpenAI API (text-embedding-3-small), распечатать размерность вектора
Ту же фразу — локально через Sentence Transformers (intfloat/multilingual-e5-small или BAAI/bge-m3 с Hugging Face)
Посчитать косинусную матрицу сходства для 3 пар фраз со вчерашнего дня — на обеих моделях, сравнить
Проверить батчинг: один вызов со списком из 10 фраз вместо 10 вызовов
Записать в конспект: эмбеддинги документов кешируются, пере-эмбеддить на каждый запрос не нужно
Контрольная точка: скрипт считает матрицу сходства на обеих моделях; вы видите, что «банк реки»/«банк денег» дают высокое сходство, и понимаете, почему это ограничение модели.

День 17 — Визуализация эмбеддингов: t-SNE / UMAP (~2 ч)
Источники:
OpenAI Cookbook — Visualizing embeddings in 2D: https://github.com/openai/openai-cookbook (examples/Visualizing_embeddings_in_2D.ipynb)
How to Visualize Embeddings with t-SNE, UMAP (Nomic): https://docs.nomic.ai/atlas/embeddings-and-retrieval/guides/how-to-visualize-embeddings
Что сделать:
Собрать датасет: 30–50 коротких текстов из 3–4 тем (спорт, кулинария, технологии, финансы) — написать самому
Получить эмбеддинги, сжать через t-SNE (scikit-learn), построить scatter-plot с раскраской по темам
Повторить с UMAP (pip install umap-learn), сравнить картинки
Поэкспериментировать с perplexity (t-SNE) и n_neighbors (UMAP) в диапазоне 5–50
Контрольная точка: темы на графике кластеризуются; понимаете, что визуализация — диагностика: если кластеров нет, проблема в модели или данных, и узнать об этом надо до сборки RAG.

День 18 — Выбор embedding-модели: MTEB и ruMTEB (~2 ч)
Источники:
Официальный MTEB Leaderboard: https://huggingface.co/spaces/mteb/leaderboard
Как читать лидерборд (Modal): https://modal.com/blog/mteb-leaderboard-article
FRIDA и ruMTEB (Хабр / SberDevices): https://habr.com/ru/companies/sberdevices/articles/909924/
Что сделать:
Открыть лидерборд, найти вкладки по категориям задач; понять, почему для RAG смотрят Retrieval и STS, а не общий средний балл
Выписать таблицу 4–5 моделей: text-embedding-3-small/large, BGE-M3, multilingual-e5-large, Qwen3-Embedding — размерность, контекст, цена/лицензия
Прочитать статью про FRIDA и ruMTEB, выписать лучшие модели для русского языка
Прогнать 5 своих русскоязычных фраз через multilingual-e5-large, сравнить сходство с результатами дня 16
Контрольная точка: можете обосновать выбор модели для двух сценариев: «англоязычный корпус, бюджет минимальный» и «русскоязычный корпус, self-hosted».

День 19 — Чанкинг: стратегии, размер, overlap (~2 ч)
Источники:
Chunking Strategies for RAG (обзор 5 стратегий): https://matheusjerico.medium.com/chunking-strategies-for-rag-fixed-recursive-semantic-language-based-and-context-aware-4ab476aea7d1
RAG Chunking Strategies: The 2026 Benchmark Guide (PremAI): https://www.premai.io/blog/rag-chunking-strategies-the-2026-benchmark-guide/
LangChain Text Splitters (официальные доки): https://docs.langchain.com/oss/python/integrations/splitters
Что сделать:
Прочитать обзор стратегий: фиксированный → рекурсивный → по предложениям → семантический → по структуре документа
Выписать правила из бенчмарков: 256–512 токенов как базовая линия, аналитика — 512–1024, overlap 10–20%
Усвоить контринтуитивное: семантический чанкинг НЕ всегда лучше рекурсивного — начинаем с рекурсивного и измеряем
Написать свой фиксированный сплиттер на чистом Python (размер в токенах через tiktoken, overlap) и рекурсивный через RecursiveCharacterTextSplitter — сравнить чанки на одном тексте
Контрольная точка: два работающих сплиттера; можете объяснить, почему размер меряют в токенах, а не символах, и чем плохи слишком мелкие чанки (128 токенов).

День 20 — Чанкинг реальных документов: PDF и таблицы (~2.5 ч)
Источники:
Your Chunks Failed Your RAG in Production (Towards Data Science): https://towardsdatascience.com/your-chunks-failed-your-rag-in-production/
Docling (официальный репозиторий): https://github.com/docling-project/docling
Unstructured vs LlamaParse vs Docling (Kanopy Labs): https://kanopylabs.com/blog/unstructured-vs-llamaparse-vs-docling-document-parsing
Что сделать:
Прочитать, почему таблицы — главная причина «тихих» провалов retrieval: двумерная структура умирает при выравнивании в текст
Установить Docling, распарсить 2–3 своих PDF (один — обязательно с таблицей)
Прогнать результат через вчерашний рекурсивный сплиттер
Вручную прочитать 15–20 чанков, выписать дефекты: разорванные таблицы, колонтитулы, битая кодировка, чанки из одного слова
Попробовать отдельную обработку таблицы: превратить строки в естественно-языковые описания перед чанкингом
Контрольная точка: есть список реальных дефектов чанкинга из ваших же документов и понимание, какой дефект как лечится.

День 21 — Мини-проект №2: индексатор документов (~3–4 ч)
Источники: заметки недели + доки Sentence Transformers (https://www.sbert.net/docs/quickstart.html). Без туториалов.
Техзадание:
CLI-скрипт: на вход — папка с 5–10 своими PDF/Markdown-файлами, на выход — индекс
Парсинг (Docling) → рекурсивный чанкинг (512 токенов, overlap 15%) → эмбеддинги (модель аргументом --model)
Каждый чанк с метаданными: источник (имя файла), номер страницы, индекс чанка
Результат — один файл index.jsonl: текст чанка + вектор + метаданные
Бонус: флаг --visualize строит UMAP-проекцию чанков, раскрашенную по файлам
Контрольная точка: индекс собирается из ваших документов, на UMAP-картинке чанки одного документа/темы группируются. Этот индекс — фундамент проекта недели 4.

НЕДЕЛЯ 4: Векторные БД и RAG-пайплайн

День 22 — ANN и HNSW на концептуальном уровне (~2 ч)
Источники:
How HNSW algorithms boost search performance (Redis Blog): https://redis.io/blog/how-hnsw-algorithms-can-improve-search/
Understanding HNSW (Zilliz Learn): https://zilliz.com/learn/hierarchical-navigable-small-worlds-HNSW
Что сделать:
Прочитать оба материала: аналогия со skip list, слои графа, «маленький мир», почему поиск идёт сверху вниз
Выписать три параметра и их компромиссы: M (связей на узел: точность vs память), efConstruction (качество графа vs скорость индексации), efSearch (точность поиска vs скорость запроса)
Нарисовать от руки схему трёхслойного HNSW и путь запроса по слоям
Понять границу: точный поиск (brute force) vs приближённый — когда что применимо
Контрольная точка: можете объяснить на пальцах, почему HNSW ищет по миллиону векторов за миллисекунды и чем при этом жертвует.

День 23 — Chroma: первая векторная БД (~2 ч)
Источники:
Chroma Getting Started (официальные доки): https://docs.trychroma.com/docs/overview/getting-started
Chroma Filters (where / where_document): https://cookbook.chromadb.dev/core/filters/
Что сделать:
pip install chromadb, поднять in-process клиент (без сервера), создать коллекцию
Загрузить вчерашний index.jsonl: текст + эмбеддинги + метаданные (add с embeddings=...)
Выполнить query по фразе — получить топ-5 чанков, посмотреть distances
Попробовать фильтры: where={"source": "файл.pdf"}, комбинации с $and/$or
Понять: Chroma может сам эмбеддить, если не передать векторы — но мы передаём свои из проекта дня 21
Контрольная точка: семантический поиск по вашим документам работает за 15 строк кода; фильтр по источнику реально сужает выдачу.

День 24 — Qdrant: метаданные, фильтрация, обновление индекса (~2.5 ч)
Источники:
Qdrant Quickstart (официальные доки): https://qdrant.tech/documentation/quickstart/
Qdrant Essentials Course (день 3 — hybrid demo, день 6 — финальный проект): https://qdrant.tech/course/essentials/day-3/hybrid-search-demo/
Что сделать:
Поднять Qdrant: docker run -p 6333:6333 qdrant/qdrant
Создать коллекцию с явной размерностью и метрикой cosine, загрузить тот же индекс через qdrant-client
Поиск с фильтром по payload (источник, страница); понять разницу pre-filtering vs post-filtering
Операции «взрослой» эксплуатации: upsert по существующему ID, set_payload, удаление по фильтру
Смоделировать сценарий «документ обновился»: переиндексировать только его чанки, не трогая остальные
Контрольная точка: умеете не только «залить и искать», но и точечно обновлять индекс — этим прототип отличается от продакшна.

День 25 — Минимальный RAG на чистом Python (~3 ч)
Источники:
RAG without LangChain and LlamaIndex (с репозиторием): https://medium.com/@advaitss11/rag-without-langchain-and-llamaindex-c1f70425dbe7
Свои конспекты недели 1 (стриминг, обработка ошибок API)
Что сделать:
Собрать полный цикл без фреймворков: вопрос → эмбеддинг вопроса → косинусный поиск по index.jsonl (numpy) → топ-3 чанка → промпт с контекстом → ответ LLM
Промпт требует: отвечать строго по контексту, цитировать источник из метаданных, при отсутствии информации — честное «не знаю»
Порог уверенности: если максимальное сходство ниже порога — fallback вместо вызова LLM
Задать 10 вопросов по своим документам, записать: где ответ хорош, где подвёл retrieval, где модель
Контрольная точка: работающий RAG на 80–100 строк; можете показать пальцем на каждую стадию — фреймворки больше не магия.

День 26 — Hybrid search и реранкинг (~2.5 ч)
Источники:
Sentence Transformers Tutorial 2026 (dense + sparse + RRF + CrossEncoder одной библиотекой): https://dataaspirant.com/blog/sentence-transformers/
Anthropic Contextual Retrieval (инженерный блог): https://www.anthropic.com/engineering/contextual-retrieval
Qdrant Hybrid Search tutorial: https://qdrant.tech/documentation/tutorials-develop/hybrid-search-fastembed/
Что сделать:
Добавить BM25 (библиотека rank_bm25) параллельно векторному поиску; слить списки через RRF (k=60) — формулу написать руками
Придумать 3 запроса, где BM25 сильнее (точный термин, код, аббревиатура), и 3, где сильнее семантика (перефразировка); убедиться, что гибрид берёт лучшее из двух
Поставить кросс-энкодер (cross-encoder/ms-marco-MiniLM-L-6-v2): переранжировать топ-20 кандидатов → оставить топ-3–5 для LLM
Сравнить ответы на 10 вчерашних вопросах: базовый RAG vs гибрид + реранкинг — записать, где стало лучше
Прочитать Contextual Retrieval как тему на вырост: контекст к чанку даёт −49% неудач retrieval, с реранкингом −67%
Контрольная точка: в пайплайне три стадии (dense + BM25 → RRF → реранкинг), и на собственных примерах видно, зачем каждая.

День 27 — Отладка и оценка retrieval (~2.5 ч)
Источники:
Retrieval Evaluation for RAG — Metrics Guide (с кодом): https://www.dataaihub.co/learn/retrieval-evaluation
Evaluating Retrieval and RAG Systems (IBM — формулы NDCG/F-beta): https://community.ibm.com/community/user/blogs/aditya-santhosh/2025/10/03/understanding-metrics-ndcg-f-beta-etc
Common RAG Failure Modes (систематика сбоев): https://theaidatabaseblog.com/learn/common-rag-failure-modes/
Что сделать:
Собрать golden-set: 30 вопросов по вашим документам, для каждого вручную отметить релевантные чанки
Реализовать метрики Recall@1/5 и MRR; посчитать для базового пайплайна и для гибрида с реранкингом
Интерпретировать по порогам: Recall@5 < 0.60 — retrieval сломан; 0.60–0.80 — чинить чанкинг/поиск; > 0.80 — переходить к генерации
Разложить вчерашние неудачи по классификации сбоев: чанкинг / retrieval / сборка контекста / генерация / устаревшие данные
Эксперимент: изменить размер чанка (256 vs 512) → пересчитать Recall@5 → записать дельту
Контрольная точка: есть число, а не ощущение — «retrieval находит нужное в топ-5 в X% случаев», и вы знаете, какой компонент менять, чтобы число росло.

День 28 — Мини-проект №3: чат по своим PDF с цитированием (~4 ч)
Источники: заметки двух недель + официальные доки по необходимости. Без туториалов.
Техзадание:
Приложение (CLI или Streamlit): чат по папке ваших документов
Пайплайн: Docling → рекурсивный чанкинг (512/15%) → эмбеддинги → Chroma или Qdrant → hybrid (dense + BM25, RRF) → кросс-энкодер → LLM
Каждый ответ содержит цитаты: источник (файл, страница) + точное предложение из чанка
Fallback: при низком скоре реранкера — «в документах нет информации», а не выдуманный ответ
Фильтры по метаданным через флаг --source файл.pdf
Команда /eval прогоняет golden-set и печатает Recall@5 и MRR
Провайдер LLM переключается флагом --provider openai|anthropic (навык недели 1)
Контрольная точка: проект работает end-to-end на реальных документах, цитирует источники, честно отказывается и измеряет своё качество — это проверка обеих недель сразу.

Итоговая самопроверка после недели 4:
Объясняю эмбеддинг, косинусное сходство, HNSW — без туториала, на пальцах
Получаю эмбеддинги через API и локально, выбираю модель по MTEB/ruMTEB
Обосновываю размер чанка и overlap для конкретного корпуса
Знаю, как ломаются PDF и таблицы, и умею это чинить
Поднимаю Chroma и Qdrant, делаю поиск с фильтрами и точечное обновление индекса
Собираю RAG на чистом Python и могу назвать, что скрывает фреймворк
Строю hybrid search (BM25 + dense + RRF) и реранкинг кросс-энкодером
Измеряю качество retrieval числом (Recall@k, MRR) по golden-set
По симптому «не находит очевидное» локализую стадию сбоя

Что дальше (неделя 5+): оценка генерации и RAGAS (курс DeepLearning.AI «Building and Evaluating Advanced RAG»: https://www.deeplearning.ai/courses/building-evaluating-advanced-rag), продвинутые паттерны (query rewriting, HyDE — репозиторий langchain-ai/rag-from-scratch), первый agentic RAG на LangGraph (официальный туториал: https://docs.langchain.com/oss/python/langgraph/agentic-rag).
