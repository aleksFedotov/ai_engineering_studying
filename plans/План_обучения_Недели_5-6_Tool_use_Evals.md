НЕДЕЛЯ 5: Function calling и структурированный вывод

День 29 — Как tool use работает под капотом (~2 ч)
Источники:
OpenAI Function calling guide: https://developers.openai.com/api/docs/guides/function-calling
How does Function Calling work in LLMs (Outcome School): https://outcomeschool.com/blog/how-does-function-calling-work-in-llms
Что сделать:
Прочитать оба материала: модель не исполняет код — она генерирует структурированный запрос (имя функции + аргументы), исполняет ваше приложение
Выписать 5-шаговый цикл: запрос со схемами инструментов → модель возвращает tool call → код исполняет → результат обратно в диалог → финальный ответ
Разобрать три элемента схемы инструмента: имя, description на естественном языке, JSON Schema параметров («пустая форма» без значений)
Нарисовать от руки диаграмму цикла для примера «какая погода в Париже» — кто на каждом шаге что делает
Записать в конспект: описания инструментов входят в промпт при каждом запросе, расходуют токены и влияют на выбор инструмента моделью
Контрольная точка: можете вслух объяснить, почему фраза «модель вызвала функцию» технически неверна, и пересказать цикл без шпаргалки.

День 30 — Первый tool call: песочницы и минимальный код (~2 ч)
Источники:
OpenAI Playground (генерация и обкатка схем): https://platform.openai.com/playground
Anthropic Console / Playground: https://console.anthropic.com/
Anthropic: How tool use works: https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works
Что сделать:
В OpenAI Playground определить function-схему get_weather(city), посмотреть, как модель запрашивает вызов и какой JSON возвращает
То же в Anthropic Console: увидеть блоки tool_use и tool_result, сравнить форматы двух провайдеров
Прочитать у Anthropic про client tools vs server tools (web_search исполняет их инфраструктура, ваши функции — ваш код)
В коде (OpenAI или Anthropic SDK) реализовать один инструмент: схема → отправка tools → разбор ответа → исполнение локальной функции → возврат результата → финальный ответ
Убедиться руками, что без возврата результата в диалог модель не знает ответа
Контрольная точка: скрипт из ~50 строк прогоняет полный цикл tool use; вы видите сырой JSON вызова и понимаете каждое поле.

День 31 — Agentic loop, параллельные вызовы и обработка ошибок (~2.5 ч)
Источники:
OpenAI Cookbook — How to call functions with chat models: https://developers.openai.com/cookbook/examples/how_to_call_functions_with_chat_models
Anthropic: Define tools (tool_choice): https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools
OpenAI Function Calling — Full Guide (Stackademic): https://blog.stackademic.com/openai-function-calling-full-guide-75d9e14db3de
Что сделать:
Прогнать ноутбук из Cookbook (SQL-пример), обратить внимание на сопоставление tool_call_id — каждое tool-сообщение ссылается на конкретный вызов
Переписать свой вчерашний скрипт на цикл while: модель может запросить несколько вызовов подряд, пока не решит задачу (у Anthropic — по stop_reason == "tool_use")
Дать модели 2 инструмента и запрос, требующий обоих сразу — наблюдать parallel tool calls; отключить через parallel_tool_calls=false и сравнить
Выписать правила, когда параллелизм вреден: зависимые вызовы (сначала customer_id, потом заказы), strict mode, деструктивные действия
Смоделировать ошибку исполнения (функция бросает исключение) → вернуть текст ошибки как tool-сообщение → посмотреть, как модель корректирует аргументы или честно признаёт проблему
Поиграть с tool_choice: auto / required / принудительный выбор конкретной функции / none (у Anthropic: auto / any / tool / none)
Контрольная точка: агентный цикл работает с 2+ инструментами, ошибки не роняют программу, а возвращаются модели; можете объяснить, почему заморозку карты нельзя делать параллельным вызовом.

День 32 — Дизайн инструментов: именование, описания, гранулярность (~2 ч)
Источники:
Anthropic: Writing effective tools for AI agents: https://www.anthropic.com/engineering/writing-tools-for-agents
OpenAI Function calling guide — раздел best practices: https://developers.openai.com/api/docs/guides/function-calling
anthropics/claude-cookbooks (GitHub, раздел tool_use): https://github.com/anthropics/claude-cookbooks
Что сделать:
Прочитать статью Anthropic: прототипировать инструмент руками до отдачи модели; обернуть инструменты в локальный MCP-сервер и потестировать через Claude Code/Desktop
Выписать три правила гранулярности из гайда OpenAI: перекладывать на код то, что знаете сами (не заставлять модель заполнять известный order_id); объединять функции, которые всегда вызываются подряд; держать < ~20 инструментов на ход
Взять 2 своих инструмента из дня 31 и переписать их description: явно указать, когда вызывать и когда НЕ вызывать
Эксперимент: дать модели размытое описание инструмента → собрать 3 случая неправильного выбора → улучшить описание → повторить
Найти в claude-cookbooks раздел tool_use и прогнать один пример «intermediate» уровня
Контрольная точка: описания ваших инструментов проходят тест «по description посторонний человек (и модель) выберет правильный инструмент»; знаете эвристику «один большой инструмент vs несколько маленьких».

День 33 — Structured Outputs: гарантии схемы и ограничения (~2 ч)
Источники:
OpenAI: Structured model outputs: https://developers.openai.com/api/docs/guides/structured-outputs
Microsoft Learn — Structured outputs (примеры с Pydantic): https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs
Что сделать:
Разобрать разницу: JSON mode гарантирует только валидный JSON, Structured Outputs — соответствие вашей схеме (grammar-constrained decoding: токены, нарушающие схему, обнуляются при генерации)
Передать Pydantic-модель через responses.parse и получить типизированный объект в output_parsed — без ручного json.loads
Выписать правила strict-схемы: все поля в required, additionalProperties: false, опциональность через ["string", "null"]
Проверить на практике ограничения: pattern/minLength не принуждаются схемой — валидировать в коде
Обработать три краевых случая по шаблону из гайда: refusal модели, обрыв по max_output_tokens, контент-фильтр
Записать в конспект капкан JSON mode: без слова «JSON» в сообщениях модель может генерировать бесконечные пробелы до исчерпания лимита
Контрольная точка: модель возвращает ответ строго по вашей Pydantic-модели со 100% валидностью формы; знаете, что схема гарантирует, а что нет.

День 34 — Instructor: валидация и авторетраи; когда что выбирать (~2.5 ч)
Источники:
DeepLearning.AI: Pydantic for LLM Workflows (1 ч 50 мин): https://www.deeplearning.ai/courses/pydantic-for-llm-workflows
Instructor docs: https://python.useinstructor.com/
Structured Outputs vs Function Calling (Machine Learning Mastery): https://machinelearningmastery.com/structured-outputs-vs-function-calling-which-should-your-agent-use/
Что сделать:
Пройти курс «Pydantic for LLM Workflows»: как современные SDK используют Pydantic под капотом для structured outputs и tool calling
Поставить instructor, описать ответ как BaseModel, увидеть авторетрай: модель вернула невалидное → библиотека переспрашивает с текстом ошибки валидации (max_retries=3)
Написать кастомный валидатор Pydantic (например, «поле дата не в прошлом») и убедиться, что ретрай учитывает его
Прочитать сравнительную статью и выписать дерево решений: structured output — про форму данных (экстракция, строгие ответы); function calling — про поток управления (нужны внешние данные или действие в середине рассуждения)
Выписать экономику: function calling = несколько round-trip'ов (дороже, медленнее, статистически непредсказуем); strict structured output = один вызов, почти 100% верность формы
Понять гибридный паттерн: оркестратор на function calling, финальный ответ пользователю — отдельным вызовом со strict structured output
Контрольная точка: можете для новой задачи обоснованно сказать «здесь хватит structured output, а здесь нужен function calling» и назвать критерий выбора (форма данных vs поток управления).

День 35 — Мини-проект №4: RAG-проект с инструментами и структурированными ответами (~4 ч)
Источники: заметки недели + официальные доки OpenAI/Anthropic. Без туториалов.
Техзадание:
Доработать чат по PDF из недели 4: добавить 2–3 инструмента через function calling
Кандидаты: search_documents(query) — модель сама решает, нужен ли поиск, и формулирует запрос (agentic RAG); get_document_metadata(doc_id) — файл, страницы, дата; calculate(expression) или доменный инструмент под ваши документы
Описания инструментов — по правилам дня 32 (когда вызывать / когда нет); известные значения подставляются в коде, а не просятся у модели
Ответы перевести на структурированный вывод: Pydantic-модель answer + citations (doc_id, page, quote) + confidence (high/medium/low) + follow_up_questions — через strict-режим или Instructor
Цитаты теперь гарантированы схемой, а не просьбой в промпте; UI/CLI рендерит их как отдельный блок
Обработка ошибок инструментов: исключение → текст ошибки модели → корректный отказ, а не падение
Контрольная точка: проект сам решает, когда искать по документам, возвращает валидный структурированный ответ с цитатами и не падает на ошибках инструментов — проверка всей недели 5.

НЕДЕЛЯ 6: Оценка качества (evals) и базовая безопасность

День 36 — Зачем нужны evals: от vibe check к измерению (~2 ч)
Источники:
Hamel Husain — Your AI Product Needs Evals: https://hamel.dev/blog/posts/evals/
OpenAI: Evaluation best practices: https://developers.openai.com/api/docs/guides/evaluation-best-practices
Anthropic: Demystifying Evals for AI Agents: https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
Что сделать:
Прочитать эссе Husain: корневая причина неуспешных LLM-продуктов — отсутствие системы оценки; «посмотрел глазами» не отвечает на вопрос «стало лучше или хуже?»
Выписать анти-паттерны из гайда OpenAI: vibe-based evals, «напишем evals перед релизом»; и альтернативу — eval-driven development (оценивать рано и часто, логировать всё)
Выписать 5-шаговый процесс: цель → датасет (логи, экспертная разметка, синтетика) → метрики → прогон и сравнение → непрерывная оценка
Из статьи Anthropic: почему evals тем труднее, чем дольше ждёшь; разница outcome vs trajectory оценки для агентов; метрики pass@k / pass^k
Записать в конспект: один и тот же промпт выдаёт разный текст при каждом запуске, поэтому проверяют свойства выхода на наборе входов, а не точное совпадение на 2–3 примерах
Контрольная точка: можете за 2 минуты убедить вымышленного коллегу, что «и так видно, что работает» — не стратегия, и назвать, что предлагаете вместо.

День 37 — Eval-набор: golden answers и краевые случаи (~2.5 ч)
Источники:
RAGAS Testset Generation: https://docs.ragas.io/en/stable/getstarted/rag_testset_generation/
OpenAI: Evaluation best practices (раздел про датасеты): https://developers.openai.com/api/docs/guides/evaluation-best-practices
Что сделать:
Сгенерировать черновик 30–50 вопросов из своих PDF через RAGAS TestsetGenerator (граф знаний из документов: single-hop ~50%, multi-hop specific ~25%, multi-hop abstract ~25%)
Вручную вычитать каждый вопрос: выбросить бессмысленные, дописать golden answers — синтетика даёт покрытие, экспертная проверка превращает её в «золотой» набор
Добавить 5–10 краевых случаев руками: вопросы без ответа в документах (правильное поведение — отказ), неоднозначные формулировки, вопросы про несколько документов сразу, 1–2 adversarial-входа
Оформить набор как данные проекта: JSONL с полями question / golden_answer / relevant_chunks / тип кейса; положить под версионирование
Свериться с консенсусом по размеру: 20–50 задач из реальных сбоев — нормальный стартовый объём; набор растёт со временем, лучшие кейсы приходят из трассировок
Контрольная точка: есть версионируемый eval-набор на 30–50 примеров, где каждый golden answer проверен вами лично, а краевые случаи покрывают «правильный отказ».

День 38 — Метрики RAG: RAGAS на живом проекте (~2.5 ч)
Источники:
RAGAS docs: https://docs.ragas.io/en/stable/
Ragas — Complete RAG Metrics Tutorial (QASkills): https://qaskills.sh/blog/ragas-llm-evaluation-guide
How to Evaluate RAG Systems (Atlan): https://atlan.com/know/how-to-evaluate-rag-systems-explained/
Что сделать:
Выписать определения четырёх метрик и что каждая диагностирует: faithfulness и answer relevancy — генерация (reference-free), context precision и context recall — ретрив
Прогнать RAGAS на вчерашнем наборе: faithfulness + answer relevancy на всех примерах, context recall + answer correctness там, где есть golden answers
Поиграть диагностическими комбинациями: высокий precision + низкий recall → увеличить top-k или размер чанка; низкий precision + высокий recall → чинить реранкинг; оба низкие → пересматривать эмбеддинги
Разобрать контринтуитивное: faithfulness 0.95 НЕ означает правильность — если извлечённый контент неверен, ответ «верен контексту», но неверен по факту; пара «высокий faithfulness + низкий correctness» = пробел ретрива
Эксперимент: изменить размер чанка (512 → 256) → перепрогнать метрики → записать дельту — как в дне 27, но теперь измеряется и генерация
Контрольная точка: каждая метрика интерпретируется как диагноз компонента; вы можете по таблице чисел сказать, что менять: чанкинг, реранкинг или промпт.

День 39 — LLM-as-a-judge: методика и смещения (~2.5 ч)
Источники:
Hamel Husain — LLM-as-a-Judge: Complete Guide: https://hamel.dev/blog/posts/llm-judge/index.html
Justice or Prejudice? — каталог смещений судей (ICLR 2025): https://llm-judge-bias.github.io/
OpenAI: Evaluation best practices (дизайн судьи): https://developers.openai.com/api/docs/guides/evaluation-best-practices
Что сделать:
Построить своего судью по методике Husain: вы — доменный эксперт; на 30–50 примерах выставить бинарные вердикты pass/fail с детальными письменными критиками (не шкалой 1–5 — бинарные решения проще валидировать)
Критики → few-shot примеры в промпт судьи; итерировать промпт, пока судья не сойдётся с вашей разметкой
Валидировать как классификатор: разбить разметку на train (few-shot) / dev (итерации) / test (один финальный прогон с замороженным промптом); считать не «сырое согласие», а TPR и TNR — на несбалансированных классах судья, всегда говорящий «pass», покажет 95% согласия при нулевом обнаружении сбоев
Выписать три смещения и контрмеры: позиционное (переставлять порядок вариантов), verbosity bias (штраф за длину в рубрике, контроль длины), self-enhancement (судья — другая модель, не та, что генерировала ответ)
Зафиксировать версию модели-судьи и промпт — обновление судьи «сдвигает шкалу» и убивает сравнения во времени
Подключить судью к вчерашнему RAGAS-прогону как дополнительную метрику (например, «ответ полностью покрывает golden answer»)
Контрольная точка: у вас откалиброванный судья с измеренным TPR/TNR на test-сплите, запиненными моделью и промптом — вы знаете, насколько ему можно доверять, числом.

День 40 — Регрессионное тестирование: promptfoo и CI (~2.5 ч)
Источники:
promptfoo — Getting started: https://www.promptfoo.dev/docs/getting-started/
Promptfoo Tutorial (DataCamp): https://www.datacamp.com/tutorial/promptfoo-tutorial
Testing LLM Prompts Like Code: Regression Evals in CI/CD (Medium): https://medium.com/@alexrodriguesj/testing-llm-prompts-like-code-regression-evals-in-ci-cd-with-promptfoo-5242b4dcb9be
Что сделать:
Поставить promptfoo, написать promptfooconfig.yaml: prompts / providers / tests с assertions — перенести часть eval-набора из дня 37
Прогнать npx promptfoo eval локально: сравнить 2 варианта системного промпта или 2 модели на одном наборе — увидеть таблицу результатов
Понять логику CI-gate: промпт = продакшн-поведение, он живёт под той же дисциплиной, что и код; assertions должны «падать громко»
Настроить GitHub Action (promptfoo/promptfoo-action@v1): eval на каждый PR, результаты в JUnit XML, порог pass-rate ~95% блокирует мёрж (не 100% — model-graded assertions недетерминированы)
Смоделировать регрессию руками: умышленно ухудшить промпт → увидеть, как eval падает до мёржа, а не после жалобы пользователя
Выписать гигиену: версии промптов и датасетов, ревью новых примеров, вывод устаревших кейсов из сьюта
Контрольная точка: изменение промпта автоматически прогоняет evals в CI; одна намеренная регрессия поймана пайплайном — вы видели, как «молчаливая деградация» превращается в красный билд.

День 41 — Базовая безопасность: prompt injection и guardrails (~2 ч)
Источники:
OWASP LLM01:2025 Prompt Injection: https://genai.owasp.org/llmrisk/llm01-prompt-injection/
Prompt Injection Defense — 4 слоя (The Road to Enterprise): https://theroadtoenterprise.com/blog/prompt-injection-ai-features-production
NeMo vs Guardrails AI vs Llama Guard vs LLM Guard (Particula): https://particula.tech/blog/ai-guardrails-compared-nemo-guardrails-ai-llama-guard
Что сделать:
Разобрать два типа инъекций: прямая (пользователь пишет «игнорируй инструкции») и косвенная (вредоносная инструкция внутри PDF, который извлёк ваш RAG) — косвенная страшнее: один отравленный документ затрагивает всех
Признать факт: prompt injection нельзя «запатчить» полностью — он эксплуатирует устройство LLM (инструкции и данные в одном канале); защита = defense in depth
Выписать 4 слоя: разделение (недоверенный контент в структурных маркерах), allowlist (инструменты только из серверного списка), валидация (отклонять вызовы вне прав пользователя), аудит (логировать каждый вызов)
Применить минимум к своему проекту: пометить retrieved-чанки как недоверенные данные в системном промпте; валидация выхода схемой уже есть с недели 5
Прогнать promptfoo redteam с плагином owasp:llm:01 против 3–5 сценариев вашего чата — посмотреть, что пробивает
Выписать осознанно отложенное: многослойные стеки guardrails, self-host классификаторов, кастомный red-teaming, compliance — это для этапа с реальными пользователями
Контрольная точка: retrieved-контент в вашем проекте официально недоверенный, инструменты за allowlist, и у вас есть отчёт red-team прогона с найденными слабостями.

День 42 — Мини-проект №5: eval-скрипт, README и финальный прогон (~4 ч)
Источники: заметки двух недель + доки RAGAS/promptfoo. Без туториалов.
Техзадание:
Собрать единый eval-скрипт проекта: eval-набор (день 37) → прогон через пайплайн недели 5 → метрики RAGAS + ваш судья (день 39) → результаты в CSV с версией промпта и модели в метаданных
Регрессионный контур из дня 40 работает на PR: порог pass-rate, дифф before/after
Оформить раздел Evaluation в README: датасет (размер, происхождение, краевые случаи, дата); таблица «метрика → что означает → значение → порог»; конфигурация прогона (версии модели/промпта/судьи); известные слабые места (3–5 failure modes со ссылкой на issues); команда воспроизведения в одну строку; мини-история «изменение → метрика до/после»
Финальный прогон всего: поменять что-то одно (промпт или размер чанка) → evals → зафиксировать дельту в README как первую запись истории
Контрольная точка: проект измеряет себя одной командой, README честно показывает качество и слабые места, а любая будущая правка пройдёт через числа, а не через ощущения — это проверка всего этапа «Недели 5–6».

Итоговая самопроверка после недели 6:
Объясняю 5-шаговый цикл tool use и могу доказать, что модель не исполняет код сама
Пишу схемы инструментов с хорошими description и реализую agentic loop с корректными tool_call_id
Объясняю, когда отключать parallel tool calls (зависимые вызовы, strict mode, деструктивные действия)
Возвращаю ошибки инструментов модели, а не роняю приложение
Различаю JSON mode и Structured Outputs; пишу strict-схемы и обрабатываю refusal/обрывы
Выбираю между structured output и function calling по критерию «форма данных vs поток управления»
Собираю eval-набор на 30–50 примеров с golden answers и краевыми случаями
Различаю faithfulness, answer relevancy, context precision/recall и читаю их комбинации как диагнозы
Строю LLM-судью: бинарные вердикты, критики как few-shot, TPR/TNR на test-сплите, запиненные модель и промпт
Называю позиционное смещение, verbosity bias и self-enhancement bias — и по контрмере к каждому
Встраиваю evals в CI с порогом pass-rate; регрессия ломает билд, а не доходит до пользователя
Объясняю прямую и косвенную prompt injection; retrieved-контент в моём проекте — недоверенный вход
В моём RAG-проекте: 2–3 инструмента, структурированные ответы с цитатами, eval-скрипт и раздел Evaluation в README

Что дальше (неделя 7+): углубление в evals агентов (курс Maven «AI Evals for Engineers & PMs» от Husain и Shankar: https://maven.com/parlance-labs/evals; курс DeepLearning.AI «Evaluating AI Agents» с трейсингом в Phoenix: https://www.deeplearning.ai/courses/evaluating-ai-agents), трейсинг и обсервабилити (LangSmith / Arize Phoenix), MCP-серверы как способ упаковки своих инструментов (статья Anthropic из дня 32 — отправная точка), агентные паттерны на LangGraph и multi-agent системы — следующий блок роадмапа.
