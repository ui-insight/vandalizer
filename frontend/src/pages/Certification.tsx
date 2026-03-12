import { useState, useEffect, useRef, useMemo } from 'react'
import {
  Award,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  Cog,
  FileOutput,
  Flame,
  FlaskConical,
  FolderGit2,
  Layers,
  Lightbulb,
  Lock,
  Play,
  Puzzle,
  ShieldCheck,
  Sparkles,
  Star,
  Target,
  X,
  Zap,
} from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useCertification } from '../hooks/useCertification'
import { cn } from '../lib/cn'
import type { ModuleDefinition, LessonSection, ValidationResult, CompletionResult, ValidationCheck } from '../types/certification'

// ---------------------------------------------------------------------------
// Module definitions
// ---------------------------------------------------------------------------

const MODULES: ModuleDefinition[] = [
  {
    id: 'foundations',
    number: 1,
    title: 'Foundations',
    subtitle: 'Documents In, Intelligence Out',
    description: 'Learn the basics of workflows: create your first extraction workflow, configure a SearchSet, and run it against a real document.',
    objectives: [
      'Create a workflow with an Extraction step',
      'Configure a SearchSet with 3+ fields',
      'Run the workflow at least once',
    ],
    tips: [
      'Start with a simple document like a grant proposal or invoice',
      'Use clear, descriptive field names in your SearchSet',
      'Test your extraction on a single document before scaling up',
    ],
    lessons: [
      {
        title: 'What is a workflow?',
        content: 'A workflow is a reusable pipeline that processes documents through a series of steps. Think of it like a recipe: you define the steps once, and then you can run that recipe against any document.\n\nWorkflows are different from ad-hoc chat. Chat is great for one-off questions about a document. But when you need to extract the same 10 fields from 500 grant proposals, you want a workflow that does it consistently every time.',
        variant: 'concept',
      },
      {
        title: 'Key terms',
        content: 'Workflow \u2014 A saved pipeline of processing steps that can be run against documents.\n\nStep \u2014 One stage in the pipeline. Each step contains one or more tasks.\n\nTask \u2014 A single operation within a step (e.g., "Extraction", "Prompt", "Format").\n\nSearchSet \u2014 A collection of fields you want to extract. Each field has a name and optional configuration like allowed values.\n\nExtract Key \u2014 A single field within a SearchSet (e.g., "PI Name", "Funding Amount", "Agency").',
        variant: 'key-terms',
      },
      {
        title: 'The document pipeline',
        content: 'When you upload a document, Vandalizer processes it through several stages:\n\n1. Text extraction \u2014 The raw text is pulled from PDFs, DOCX, XLSX, and HTML files using specialized readers.\n2. Chunking \u2014 The text is split into overlapping segments for semantic search.\n3. Embedding \u2014 Each chunk is embedded into ChromaDB, a vector database, so it can be searched semantically.\n\nWhen a workflow runs an Extraction step, the LLM receives the full document text and your SearchSet fields, and returns structured JSON with the extracted values.',
        variant: 'concept',
      },
      {
        title: 'Build your first workflow',
        content: '1. Go to the Workspace and open the Workflow editor (or navigate to Workflows and create a new one).\n2. Give your workflow a clear name, like "Grant Proposal Extractor".\n3. Add a step, then add an Extraction task to that step.\n4. In the Extraction task settings, select an existing SearchSet or create a new one.\n5. Add at least 3 fields to your SearchSet \u2014 for example: "Principal Investigator", "Funding Amount", "Sponsoring Agency".\n6. Select a document in your workspace, then click Run to execute the workflow.\n7. Review the extracted results in the output panel.',
        variant: 'walkthrough',
      },
      {
        title: 'Why structured extraction matters',
        content: 'Unstructured AI responses vary every time \u2014 different formatting, different phrasing, different levels of detail. Structured extraction forces the AI to return consistent, machine-readable JSON. This means you can reliably extract the same fields from hundreds of documents and compare, aggregate, or export the results. It turns documents from unstructured text into queryable data.',
        variant: 'insight',
      },
    ],
    xp: 100,
    icon: 'BookOpen',
  },
  {
    id: 'extraction_engine',
    number: 2,
    title: 'Extraction Engine',
    subtitle: 'Master the Extraction Pipeline',
    description: 'Explore one-pass vs. two-pass extraction strategies, configure large field sets, and understand how the extraction engine maximizes accuracy.',
    objectives: [
      'Create a SearchSet with 15+ fields',
    ],
    tips: [
      'Two-pass extraction uses a draft-then-refine approach for higher accuracy',
      'Use enum_values to constrain fields to known categories',
      'Mark fields as optional when they may not appear in every document',
    ],
    lessons: [
      {
        title: 'One-pass vs. two-pass extraction',
        content: 'Vandalizer offers two extraction strategies:\n\nOne-pass extraction sends the document and field definitions to the LLM in a single call. It\'s faster and cheaper, but can miss nuances in complex documents.\n\nTwo-pass extraction (the default) works in two stages:\n\u2022 Pass 1: The LLM creates a draft extraction, thinking through each field.\n\u2022 Pass 2: A second LLM call refines the draft, using structured output to produce clean, validated JSON.\n\nThe two-pass approach is more accurate because the second pass can correct mistakes from the first, and the structured output format prevents formatting errors.',
        variant: 'concept',
      },
      {
        title: 'Key terms',
        content: 'Structured Output \u2014 The LLM is constrained to return data matching a specific schema (built from your SearchSet fields as a dynamic Pydantic model). This prevents formatting errors and hallucinated fields.\n\nThinking Mode \u2014 When enabled, the LLM reasons step-by-step before answering. Pass 1 uses thinking for accuracy; Pass 2 disables it for speed.\n\nConsensus Repetition \u2014 An optional mode that runs extraction 3 times in parallel and uses majority voting to resolve disagreements. 3x the cost, but highest accuracy for critical fields.\n\nChunking \u2014 When you have many fields (20+), the extraction can be split into smaller batches to avoid overwhelming the LLM\'s context window.',
        variant: 'key-terms',
      },
      {
        title: 'Configuring fields for accuracy',
        content: 'The way you configure your SearchSet fields directly impacts extraction quality:\n\nField names should be specific and unambiguous. "PI Name" is better than "Name". "Total Budget (USD)" is better than "Budget".\n\nEnum values constrain a field to a set of allowed options. For a field like "Document Type", you might set enum values to ["Grant Proposal", "Progress Report", "Budget Justification"]. This prevents the LLM from inventing categories.\n\nOptional fields should be marked as such. If a field like "Co-PI" won\'t appear in every document, marking it optional tells the extraction engine not to hallucinate a value when one doesn\'t exist.\n\nField descriptions (in the title/searchphrase) give the LLM additional context about what to look for.',
        variant: 'concept',
      },
      {
        title: 'Build a comprehensive extraction',
        content: '1. Create a new SearchSet or expand an existing one to 15+ fields.\n2. Group related fields logically \u2014 e.g., personnel fields together, budget fields together.\n3. Use enum_values for any categorical field (status, type, category).\n4. Mark fields that may not always be present as optional.\n5. Add descriptive titles to help the LLM understand ambiguous fields.\n6. Run the extraction on a test document and review the results.\n7. Iterate: adjust field names and add enum constraints for any fields that extracted poorly.',
        variant: 'walkthrough',
      },
      {
        title: 'When to use consensus repetition',
        content: 'Consensus repetition runs the same extraction 3 times and takes the majority answer for each field. Use it when the stakes are high \u2014 compliance data, financial figures, legal terms \u2014 and the cost of an incorrect extraction outweighs the 3x processing cost. For routine extractions or exploratory work, two-pass is usually sufficient.',
        variant: 'insight',
      },
    ],
    xp: 150,
    icon: 'FlaskConical',
  },
  {
    id: 'multi_step',
    number: 3,
    title: 'Multi-Step Workflows',
    subtitle: 'Chain Steps Together',
    description: 'Build workflows with multiple steps that chain together. Learn how extraction, prompt, and format steps work in sequence to produce rich outputs.',
    objectives: [
      'Build a workflow with 3+ steps',
      'Include Extraction, Prompt, and Format task types in one workflow',
    ],
    tips: [
      'Each step receives the previous step\'s output as input',
      'Use Prompt steps to reason over extracted data',
      'Format steps transform structured data into readable reports',
    ],
    lessons: [
      {
        title: 'How steps chain together',
        content: 'A multi-step workflow forms a pipeline where each step\'s output becomes the next step\'s input. The workflow engine executes steps in order (technically, in topological order of a directed acyclic graph, or DAG).\n\nFor example, a 3-step workflow might work like this:\n\u2022 Step 1 (Extraction): Pulls structured fields from the document \u2192 outputs JSON.\n\u2022 Step 2 (Prompt): Receives that JSON and asks the LLM to analyze it \u2192 outputs analysis text.\n\u2022 Step 3 (Format): Takes the analysis and formats it into a clean report \u2192 outputs final document.\n\nEach step can see the output of the step before it, creating a chain of increasingly refined output.',
        variant: 'concept',
      },
      {
        title: 'Key terms',
        content: 'Input Source \u2014 Controls what data a step receives. Options:\n\u2022 "step_input" \u2014 Uses the previous step\'s output (default, used for chaining).\n\u2022 "select_document" \u2014 Uses a specific pre-loaded document instead of the previous output.\n\u2022 "workflow_documents" \u2014 Uses all documents selected when the workflow was triggered.\n\nPrompt Node \u2014 Sends data to the LLM with a custom prompt. Great for analysis, summarization, comparison, or decision-making based on extracted data.\n\nFormat Node \u2014 Transforms structured data into formatted text (markdown, plain text, etc.). Use it to turn raw JSON into human-readable reports.\n\nPost-process Prompt \u2014 An optional final LLM call on any node\'s output. Use it to clean up or reformat results without adding a separate step.',
        variant: 'key-terms',
      },
      {
        title: 'The Prompt node: reasoning over data',
        content: 'The Prompt node is one of the most powerful tools in your workflow. It sends the previous step\'s output to the LLM along with your custom prompt, and returns the LLM\'s response.\n\nUse it to:\n\u2022 Summarize extracted data ("Given these extracted fields, write a one-paragraph summary of this grant proposal")\n\u2022 Compare and analyze ("Based on the budget breakdown, identify any line items that exceed 25% of the total")\n\u2022 Generate recommendations ("Given this compliance data, flag any potential issues")\n\u2022 Transform formats ("Convert this JSON into a bulleted list of key findings")\n\nThe key insight is that extraction gives you structured data, and prompts let you reason over that data.',
        variant: 'concept',
      },
      {
        title: 'Build a 3-step analysis workflow',
        content: '1. Create a new workflow and add 3 steps.\n2. Step 1 \u2014 Add an Extraction task. Select a SearchSet with fields relevant to your document.\n3. Step 2 \u2014 Add a Prompt task. Write a prompt that analyzes the extracted data (e.g., "Summarize the key findings and flag any concerns based on the following extracted data:").\n4. Step 3 \u2014 Add a Formatter task. Write a template that structures the final output (e.g., "## Analysis Report\\n\\n{{input}}").\n5. Select a document and run the workflow. Observe how data flows through each step.\n6. Review each step\'s output individually using the step-by-step output panel.',
        variant: 'walkthrough',
      },
      {
        title: 'Design principle: extract first, reason second',
        content: 'A common mistake is trying to do everything in one big prompt. Instead, separate extraction (getting facts from documents) from reasoning (drawing conclusions from those facts). This makes each step simpler, more reliable, and easier to debug. If your final output is wrong, you can check: did the extraction step get the right data? Or did the prompt step misinterpret it? This separation is what makes workflows more reliable than one-shot prompting.',
        variant: 'insight',
      },
    ],
    xp: 150,
    icon: 'Layers',
  },
  {
    id: 'advanced_nodes',
    number: 4,
    title: 'Advanced Nodes',
    subtitle: 'Parallel Tasks & Power Nodes',
    description: 'Use advanced node types like Code Execution and API Call. Run multiple tasks in parallel within a single step for concurrent processing.',
    objectives: [
      'Use an advanced node (Code, API, Research, Crawler, or Browser)',
      'Run 2+ tasks in parallel within a single step',
    ],
    tips: [
      'Code Execution nodes run sandboxed Python with a 10-second timeout',
      'API Call nodes can fetch data from external services to enrich workflows',
      'Parallel tasks within a step run concurrently for faster execution',
    ],
    lessons: [
      {
        title: 'Beyond extraction and prompts',
        content: 'Vandalizer has 17 different node types. So far you\'ve used Extraction, Prompt, and Format \u2014 but the advanced nodes let you go much further:\n\n\u2022 Code Execution \u2014 Run sandboxed Python to transform data, do calculations, or apply custom logic.\n\u2022 API Call \u2014 Make HTTP requests to external services (REST APIs, webhooks, data sources).\n\u2022 Research \u2014 Two-pass analysis: first analyzes the data, then synthesizes findings into a structured report.\n\u2022 Crawler \u2014 Fetch and extract text from websites, following links from a starting URL.\n\u2022 Add Document / Add Website \u2014 Inject additional context from other documents or web pages mid-workflow.\n\u2022 Browser Automation \u2014 Drive a Chrome browser session for complex web interactions.',
        variant: 'concept',
      },
      {
        title: 'Key terms',
        content: 'Parallel Tasks \u2014 Multiple tasks within a single step run concurrently using a thread pool. Their results are collected and passed to the next step together. Use this when you need multiple independent operations at the same stage.\n\nCode Execution \u2014 Runs Python in a restricted sandbox with a 10-second timeout. The previous step\'s output is available as the variable `input_data`. Your code should assign its result to `output`.\n\nAPI Call \u2014 Supports GET, POST, PUT, and PATCH methods. You can include headers for authentication and use the previous step\'s output in the request body.\n\nResearch Node \u2014 Performs two-stage analysis: first passes through the data to identify patterns, then synthesizes findings into a coherent report. More thorough than a single Prompt node for complex analysis.',
        variant: 'key-terms',
      },
      {
        title: 'Code Execution: custom logic in your pipeline',
        content: 'The Code Execution node lets you write Python that runs inside your workflow. This is powerful for:\n\n\u2022 Data transformation \u2014 Normalize dates, convert currencies, merge fields.\n\u2022 Calculations \u2014 Compute totals, percentages, or ratios from extracted numbers.\n\u2022 Filtering \u2014 Remove irrelevant results or flag outliers.\n\u2022 Format conversion \u2014 Reshape JSON into a different structure.\n\nThe code runs in a sandbox: no file system access, no network access, no imports beyond the standard library. Your code receives the previous step\'s output as `input_data` and should assign its result to `output`. Execution times out after 10 seconds.',
        variant: 'concept',
      },
      {
        title: 'Running tasks in parallel',
        content: 'Within a single step, you can add multiple tasks. These tasks run concurrently \u2014 the workflow engine uses a thread pool to execute them simultaneously.\n\nThis is useful when you need multiple independent operations:\n\u2022 Extract from two different SearchSets at the same time\n\u2022 Call multiple APIs in parallel\n\u2022 Run an extraction while simultaneously fetching enrichment data from a website\n\nTo add parallel tasks, open a step in the workflow editor and click "Add Task" multiple times. Each task within the step runs independently and their results are combined before passing to the next step.',
        variant: 'concept',
      },
      {
        title: 'Build a workflow with advanced nodes',
        content: '1. Create a workflow with at least 3 steps.\n2. In one step, add a Code Execution task. Write Python that transforms the previous step\'s output (e.g., normalize currency values, compute a total, or filter results).\n3. Or, add an API Call task that fetches data from an external source to enrich your extraction.\n4. In another step, add 2 tasks to run in parallel. For example, run two different extractions on the same document at the same time.\n5. Run the workflow and review how parallel tasks\' outputs are combined.',
        variant: 'walkthrough',
      },
    ],
    xp: 200,
    icon: 'Puzzle',
  },
  {
    id: 'output_delivery',
    number: 5,
    title: 'Output & Delivery',
    subtitle: 'Produce Real Deliverables',
    description: 'Generate downloadable reports, CSV exports, ZIP archives, and pre-filled forms. Make your workflows produce ready-to-submit deliverables.',
    objectives: [
      'Use a Document Renderer, Data Export, Package Builder, or Form Filler',
      'Run the workflow to produce downloadable output',
    ],
    tips: [
      'Document Renderer creates downloadable markdown/text files',
      'Data Export supports JSON and CSV formats',
      'Package Builder creates ZIP archives with multiple output files',
    ],
    lessons: [
      {
        title: 'From analysis to deliverables',
        content: 'So far, your workflows produce text output that you view in the app. But real research administration often requires deliverables: compliance reports to submit, data exports for spreadsheets, or document packages with multiple files.\n\nVandalizer\'s output nodes transform your workflow results into downloadable files:\n\n\u2022 Document Renderer \u2014 Generates a markdown or text file from your workflow output. Great for reports, summaries, and formatted documents.\n\u2022 Data Export \u2014 Exports structured data as JSON or CSV. Perfect for loading into Excel, databases, or other tools.\n\u2022 Package Builder \u2014 Creates a ZIP archive containing multiple output files. Use it when a workflow produces several deliverables.\n\u2022 Form Filler \u2014 Takes a template with placeholders and fills it with extracted data. Ideal for pre-populating compliance forms or standard documents.',
        variant: 'concept',
      },
      {
        title: 'Key terms',
        content: 'Document Renderer \u2014 Takes the previous step\'s text output and wraps it into a downloadable file. The output is a base64-encoded file object that the frontend can download.\n\nData Export \u2014 Converts structured JSON data into CSV (spreadsheet) or JSON format. When using CSV, each key becomes a column header.\n\nPackage Builder \u2014 Collects outputs from multiple steps and bundles them into a single ZIP file for download.\n\nForm Filler \u2014 Uses a template string with placeholder syntax. The engine replaces placeholders with values from the extracted data, producing a filled-in version of your template.\n\nIs Output \u2014 A flag on steps that marks them as output steps. Only steps marked "is_output" contribute to the final downloadable result.',
        variant: 'key-terms',
      },
      {
        title: 'Designing end-to-end deliverable workflows',
        content: 'The most powerful workflows go from raw document to finished deliverable in one run:\n\n1. Extract \u2014 Pull structured data from the source document.\n2. Analyze \u2014 Use Prompt nodes to reason over the data, flag issues, or generate summaries.\n3. Render \u2014 Use output nodes to produce the final deliverable.\n\nFor example, a compliance review workflow might:\n\u2022 Step 1: Extract 20 compliance-relevant fields from a grant proposal.\n\u2022 Step 2: Prompt the LLM to check each field against compliance rules.\n\u2022 Step 3: Format the results into a compliance checklist.\n\u2022 Step 4: Render the checklist as a downloadable document.\n\nThe result: upload a grant proposal, click Run, and download a completed compliance checklist.',
        variant: 'concept',
      },
      {
        title: 'Build a deliverable workflow',
        content: '1. Start with a workflow that extracts and analyzes data (from Module 3).\n2. Add a new step at the end of your workflow.\n3. Add a Document Renderer or Data Export task to that step.\n4. For Document Renderer: the previous step\'s output will be rendered as a downloadable file.\n5. For Data Export: choose JSON or CSV format. CSV works best when your data is flat (key-value pairs).\n6. Run the workflow on a document.\n7. In the results panel, you\'ll see a download link for the generated file.',
        variant: 'walkthrough',
      },
    ],
    xp: 200,
    icon: 'FileOutput',
  },
  {
    id: 'validation_qa',
    number: 6,
    title: 'Validation & QA',
    subtitle: 'Ensure Quality at Scale',
    description: 'Define validation plans, create quality checks, and track workflow reliability over time. Build confidence that your workflows produce correct results.',
    objectives: [
      'Create a validation plan with 2+ quality checks',
      'Run a validated workflow',
    ],
    tips: [
      'Validation plans can be auto-generated from your workflow structure',
      'Track quality history to spot regressions over time',
      'Use improvement suggestions to iteratively refine your extraction',
    ],
    lessons: [
      {
        title: 'Why validation matters',
        content: 'An extraction workflow that works on one document might fail on the next. Different document layouts, writing styles, or terminology can cause the LLM to miss fields or return incorrect values.\n\nValidation lets you define what "correct" looks like for your workflow, test it against sample documents, and track reliability over time. It\'s the difference between "I think this workflow works" and "I know this workflow works because it passes 15 quality checks across 10 test documents."',
        variant: 'concept',
      },
      {
        title: 'Key terms',
        content: 'Validation Plan \u2014 A list of quality checks that define what correct output looks like for your workflow. Each check has criteria and an expected outcome.\n\nValidation Input \u2014 Sample documents or text used to test the workflow. These should represent the variety of documents the workflow will encounter in production.\n\nValidation Run \u2014 An execution of the workflow against validation inputs, with results graded against the validation plan.\n\nQuality History \u2014 A log of validation run scores over time. Use it to detect regressions when you change your workflow or when models are updated.\n\nImprovement Suggestions \u2014 LLM-generated tips for improving extraction accuracy based on validation results.',
        variant: 'key-terms',
      },
      {
        title: 'Building effective validation plans',
        content: 'Good validation plans check multiple dimensions of quality:\n\n\u2022 Completeness \u2014 Did the workflow extract all expected fields? Are any null that shouldn\'t be?\n\u2022 Accuracy \u2014 Do extracted values match the known-correct values from your test documents?\n\u2022 Format \u2014 Are dates in the right format? Are numbers parsed correctly? Are enum values within the allowed set?\n\u2022 Consistency \u2014 When run multiple times on the same document, does the workflow produce the same results?\n\nStart with 2-3 high-value checks (e.g., "PI Name is not null", "Funding Amount is a valid number") and expand as you gain confidence in the basics.',
        variant: 'concept',
      },
      {
        title: 'Set up validation for your workflow',
        content: '1. Open your workflow in the editor and go to the Validate tab.\n2. Add validation inputs \u2014 paste sample text or select documents that represent your typical input.\n3. Create a validation plan with at least 2 quality checks. You can auto-generate checks based on your workflow structure.\n4. Run validation. The system executes your workflow against each validation input and grades the results.\n5. Review the results: which checks passed, which failed, and why.\n6. Use improvement suggestions to iterate on your extraction fields or prompts.\n7. Check quality history to see how your workflow improves over time.',
        variant: 'walkthrough',
      },
      {
        title: 'Validation as a safety net',
        content: 'The best time to set up validation is before you need it. When you change your SearchSet fields, update a prompt, or when the underlying LLM model is updated, your workflow\'s behavior might change. If you have a validation plan, you can re-run it immediately to check for regressions. Without validation, you might not notice a problem until it affects real work.',
        variant: 'insight',
      },
    ],
    xp: 250,
    icon: 'ShieldCheck',
  },
  {
    id: 'batch_processing',
    number: 7,
    title: 'Batch Processing',
    subtitle: 'Process at Scale',
    description: 'Run workflows against multiple documents simultaneously. Monitor batch execution, handle failures, and optimize for throughput.',
    objectives: [
      'Run a workflow in batch mode against 3+ documents',
      'All documents in the batch must complete successfully',
    ],
    tips: [
      'Batch mode runs your workflow once per document sequentially',
      'Monitor progress via the real-time status feed',
      'Test with a single document first, then scale to batch',
    ],
    lessons: [
      {
        title: 'Single vs. batch execution',
        content: 'So far you\'ve been running workflows on one document at a time. Batch mode lets you process multiple documents in a single operation.\n\nIn batch mode, the workflow runs once per document, sequentially. Each document gets its own WorkflowResult, and you can monitor progress for the entire batch.\n\nThis is the core value proposition of Vandalizer: define a workflow once, validate it, then run it across hundreds of documents with confidence.',
        variant: 'concept',
      },
      {
        title: 'Key terms',
        content: 'Batch Mode \u2014 Runs the workflow once per selected document. Each execution is independent \u2014 a failure on one document doesn\'t stop the others.\n\nBatch ID \u2014 A unique identifier for the batch. All results from the same batch share this ID, letting you track overall progress.\n\nSession ID \u2014 Each individual document execution within a batch has its own session ID for detailed status tracking.\n\nBatch Status \u2014 Aggregated view of all executions: how many completed, failed, or are still running. Polled via the batch status endpoint.',
        variant: 'key-terms',
      },
      {
        title: 'Monitoring and debugging batch runs',
        content: 'When running a batch:\n\n\u2022 Real-time progress \u2014 The UI shows which document is currently processing, what step it\'s on, and a preview of intermediate results. This uses Server-Sent Events (SSE) for live updates.\n\u2022 Per-document results \u2014 Each document\'s result is stored independently. If one fails, you can inspect that specific result to see which step failed and why.\n\u2022 Error handling \u2014 Common failures include documents that are too long for the model\'s context window, documents in unexpected formats, or documents that don\'t contain the expected fields. Review the error details to decide whether to fix the workflow or exclude the document.\n\nAlways test your workflow on a single representative document before running a batch. This catches most configuration issues before they waste processing time on 100 documents.',
        variant: 'concept',
      },
      {
        title: 'Choosing the right model for batch work',
        content: 'Model selection matters more for batch processing because costs and time multiply across documents. Consider:\n\n\u2022 Speed \u2014 Faster models (like smaller variants) can cut batch processing time significantly.\n\u2022 Cost \u2014 Token usage across 100 documents adds up. Use the activity log to estimate per-document cost, then multiply.\n\u2022 Accuracy \u2014 More capable models produce better extractions but cost more. The sweet spot depends on your quality requirements.\n\u2022 Data privacy \u2014 Some models run locally or on-premises, which may be required for sensitive documents.\n\nYou can override the model per-workflow or per-task. Consider using a faster model for format/prompt steps and a more capable model for extraction steps.',
        variant: 'insight',
      },
      {
        title: 'Run your first batch',
        content: '1. Ensure you have a workflow that works reliably on a single document (from previous modules).\n2. Upload at least 3 documents of the same type to your workspace.\n3. Select all 3 documents, then open your workflow.\n4. Choose "Batch" mode (instead of running on all documents together).\n5. Start the batch. Watch the real-time progress as each document is processed.\n6. When complete, review the results for each document. Check that all 3 completed successfully.\n7. If any failed, inspect the error, fix the issue, and re-run just the failed documents.',
        variant: 'walkthrough',
      },
    ],
    xp: 250,
    icon: 'Play',
  },
  {
    id: 'governance',
    number: 8,
    title: 'Collaboration & Governance',
    subtitle: 'Share and Standardize',
    description: 'Organize workflows across spaces, share validated workflows with your team, and establish governance practices for production-grade workflows.',
    objectives: [
      'Mark a workflow as verified',
      'Use workflows across 2+ spaces',
    ],
    tips: [
      'Export workflows as .vandalizer.json files to share with teammates',
      'Verified workflows signal to your team that a workflow is production-ready',
      'Use spaces to organize workflows by project, team, or document type',
    ],
    lessons: [
      {
        title: 'Organizing with spaces',
        content: 'As your team builds more workflows, organization becomes critical. Spaces provide logical grouping for documents, workflows, and folders.\n\nThink of spaces like projects or departments:\n\u2022 "NSF Grants" \u2014 All workflows and documents related to NSF grant processing.\n\u2022 "Compliance" \u2014 Workflows for compliance review across all agencies.\n\u2022 "Internal Reports" \u2014 Workflows for generating internal summaries.\n\nDocuments and workflows are scoped by space, so different teams or projects can work independently without interfering with each other.',
        variant: 'concept',
      },
      {
        title: 'Key terms',
        content: 'Space \u2014 A logical grouping of documents, workflows, and folders. Used to organize work by project, department, or document type.\n\nVerified \u2014 A flag on a workflow indicating it has been tested, validated, and approved for production use. A signal to your team that this workflow is trusted.\n\nExport (.vandalizer.json) \u2014 A JSON file containing the complete workflow definition (steps, tasks, configuration). Can be shared with teammates or imported into other spaces.\n\nTeam \u2014 A group of users who share access to spaces and workflows. Members have roles: owner, admin, or member.',
        variant: 'key-terms',
      },
      {
        title: 'The verification workflow',
        content: 'Marking a workflow as "verified" is a governance practice. It signals to your team that:\n\n1. The workflow has been tested on representative documents.\n2. A validation plan exists and passes consistently.\n3. The output format meets the team\'s requirements.\n4. The workflow is ready for production use.\n\nBefore verifying, ensure:\n\u2022 You\'ve run the workflow on at least several documents.\n\u2022 You\'ve set up and passed a validation plan (Module 6).\n\u2022 You\'ve reviewed the output format with stakeholders.\n\u2022 You\'ve documented what the workflow does (in its description field).\n\nVerification isn\'t a technical gate \u2014 it\'s a team communication tool. It says "I\'ve done the due diligence."',
        variant: 'concept',
      },
      {
        title: 'Sharing workflows across teams',
        content: 'Workflows can be shared in two ways:\n\n\u2022 Same team, different spaces \u2014 Create workflows in one space, then organize them across spaces as your needs grow. A workflow in the "NSF Grants" space can be duplicated into "NIH Grants" and adapted.\n\u2022 Cross-team sharing via export/import \u2014 Export a workflow as a .vandalizer.json file. Send it to a colleague, who can import it into their own space. The import preserves all steps, tasks, and configuration. SearchSets may need to be recreated or linked.\n\nSharing verified workflows establishes organizational standards. Instead of each team member building their own extraction workflow, one person builds and validates it, then shares it with everyone.',
        variant: 'concept',
      },
      {
        title: 'Establish your workflow governance',
        content: '1. If you don\'t already have multiple spaces, create a second space from the Spaces page.\n2. Build or duplicate a workflow in this new space.\n3. Make sure your workflow has a clear description explaining what it does and what documents it\'s designed for.\n4. If you completed Module 6, ensure your validation plan passes.\n5. Mark the workflow as verified in the workflow settings.\n6. Try exporting the workflow as a .vandalizer.json file and importing it into your other space.\n7. You now have a verified, portable, well-documented workflow that your team can trust.',
        variant: 'walkthrough',
      },
      {
        title: 'Building a culture of reuse',
        content: 'The highest-performing teams don\'t build workflows from scratch every time. They maintain a library of verified workflows that cover common document types, then adapt and extend them as needed. When a new grant format comes in, they duplicate an existing verified workflow and adjust the SearchSet \u2014 rather than starting over. Certification is your first step toward building this culture on your team.',
        variant: 'insight',
      },
    ],
    xp: 300,
    icon: 'FolderGit2',
  },
]

const LEVEL_CONFIG: Record<string, { label: string; color: string }> = {
  novice:     { label: 'Novice',     color: '#9ca3af' },
  apprentice: { label: 'Apprentice', color: '#60a5fa' },
  builder:    { label: 'Builder',    color: '#34d399' },
  designer:   { label: 'Designer',   color: '#a78bfa' },
  engineer:   { label: 'Engineer',   color: '#f472b6' },
  specialist: { label: 'Specialist', color: '#fb923c' },
  expert:     { label: 'Expert',     color: '#f43f5e' },
  master:     { label: 'Master',     color: '#eab308' },
  architect:  { label: 'Architect',  color: '#eab308' },
}

const LEVEL_THRESHOLDS = [
  { name: 'novice', xp: 0 },
  { name: 'apprentice', xp: 100 },
  { name: 'builder', xp: 250 },
  { name: 'designer', xp: 400 },
  { name: 'engineer', xp: 600 },
  { name: 'specialist', xp: 800 },
  { name: 'expert', xp: 1050 },
  { name: 'master', xp: 1300 },
  { name: 'architect', xp: 1600 },
]

const ICON_MAP: Record<string, React.ComponentType<{ className?: string; size?: number }>> = {
  BookOpen,
  FlaskConical,
  Layers,
  Puzzle,
  FileOutput,
  ShieldCheck,
  Play,
  FolderGit2,
}

const TOTAL_XP = 1600

// ---------------------------------------------------------------------------
// Progress ring component
// ---------------------------------------------------------------------------

function ProgressRing({ percentage, size = 160, strokeWidth = 10, color }: {
  percentage: number
  size?: number
  strokeWidth?: number
  color: string
}) {
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (percentage / 100) * circumference
  const [animatedOffset, setAnimatedOffset] = useState(circumference)

  useEffect(() => {
    const timer = setTimeout(() => setAnimatedOffset(offset), 100)
    return () => clearTimeout(timer)
  }, [offset])

  return (
    <svg width={size} height={size} className="cert-ring-spin">
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="#e5e7eb"
        strokeWidth={strokeWidth}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={animatedOffset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(0.4, 0, 0.2, 1)' }}
      />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Star display
// ---------------------------------------------------------------------------

function Stars({ count, max = 3, size = 16 }: { count: number; max?: number; size?: number }) {
  return (
    <div className="flex gap-0.5">
      {Array.from({ length: max }).map((_, i) => (
        <Star
          key={i}
          size={size}
          className={cn(
            'transition-all duration-300',
            i < count ? 'text-yellow-400 fill-yellow-400' : 'text-gray-300',
          )}
          style={i < count ? { animationDelay: `${i * 0.15}s` } : undefined}
        />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// XP bar
// ---------------------------------------------------------------------------

function XPBar({ current, nextThreshold, prevThreshold, nextLevel }: {
  current: number
  nextThreshold: number
  prevThreshold: number
  nextLevel: string
}) {
  const range = nextThreshold - prevThreshold
  const progress = Math.min(((current - prevThreshold) / range) * 100, 100)

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-medium text-gray-500">{current} XP</span>
        <span className="text-xs text-gray-400">
          {nextThreshold - current} XP to {LEVEL_CONFIG[nextLevel]?.label || 'Max'}
        </span>
      </div>
      <div className="h-2.5 bg-gray-200 overflow-hidden" style={{ borderRadius: 'var(--ui-radius, 12px)' }}>
        <div
          className="h-full cert-xp-glow"
          style={{
            width: `${progress}%`,
            background: `linear-gradient(90deg, var(--highlight-color), var(--highlight-complement))`,
            borderRadius: 'var(--ui-radius, 12px)',
            transition: 'width 1s cubic-bezier(0.4, 0, 0.2, 1)',
          }}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Module card
// ---------------------------------------------------------------------------

function ModuleCard({ module, completed, stars, locked, active, onClick }: {
  module: ModuleDefinition
  completed: boolean
  stars: number
  locked: boolean
  active: boolean
  onClick: () => void
}) {
  const Icon = ICON_MAP[module.icon] || BookOpen

  return (
    <button
      onClick={onClick}
      disabled={locked}
      className={cn(
        'relative flex flex-col items-start p-5 text-left border-2 transition-all duration-300',
        'hover:shadow-lg group',
        locked && 'opacity-50 cursor-not-allowed hover:shadow-none',
        completed && !active && 'border-green-200 bg-green-50/50',
        active && 'border-highlight bg-highlight/5 shadow-lg',
        !completed && !active && !locked && 'border-gray-200 bg-white hover:border-highlight',
      )}
      style={{ borderRadius: 'var(--ui-radius, 12px)' }}
    >
      {/* Module number badge */}
      <div
        className={cn(
          'absolute -top-3 -left-1 w-7 h-7 flex items-center justify-center text-xs font-bold',
          completed ? 'bg-green-500 text-white' : locked ? 'bg-gray-300 text-gray-500' : 'bg-highlight text-highlight-text',
        )}
        style={{ borderRadius: 'var(--ui-radius, 12px)' }}
      >
        {completed ? <Check size={14} /> : module.number}
      </div>

      {/* Lock overlay */}
      {locked && (
        <div className="absolute inset-0 flex items-center justify-center" style={{ borderRadius: 'var(--ui-radius, 12px)' }}>
          <Lock size={24} className="text-gray-400" />
        </div>
      )}

      {/* Icon + Title */}
      <div className={cn('flex items-center gap-2 mb-2 mt-1', locked && 'invisible')}>
        <Icon
          size={20}
          className={cn(
            completed ? 'text-green-600' : 'text-gray-600 group-hover:text-highlight',
            'transition-colors',
          )}
        />
        <span className="font-semibold text-sm text-gray-900">{module.title}</span>
      </div>

      <p className={cn('text-xs text-gray-500 mb-3 line-clamp-2', locked && 'invisible')}>
        {module.subtitle}
      </p>

      {/* Bottom row: stars + XP */}
      <div className={cn('flex items-center justify-between w-full mt-auto', locked && 'invisible')}>
        <Stars count={stars} size={14} />
        <span
          className={cn(
            'text-xs font-bold px-2 py-0.5',
            completed ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600',
          )}
          style={{ borderRadius: 'var(--ui-radius, 12px)' }}
        >
          {module.xp} XP
        </span>
      </div>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Lesson section renderer
// ---------------------------------------------------------------------------

const VARIANT_STYLES: Record<LessonSection['variant'], { icon: React.ComponentType<{ size?: number; className?: string }>; border: string; bg: string; label: string }> = {
  concept:     { icon: BookOpen,    border: 'border-blue-200',   bg: 'bg-blue-50/50',    label: 'Concept' },
  walkthrough: { icon: Play,        border: 'border-green-200',  bg: 'bg-green-50/50',   label: 'Walkthrough' },
  'key-terms': { icon: BookOpen,    border: 'border-purple-200', bg: 'bg-purple-50/50',  label: 'Key Terms' },
  insight:     { icon: Lightbulb,   border: 'border-amber-200',  bg: 'bg-amber-50/50',   label: 'Insight' },
}

function LessonRenderer({ section }: { section: LessonSection }) {
  const style = VARIANT_STYLES[section.variant]
  const Icon = style.icon

  return (
    <div
      className={cn('border-l-4 p-4', style.border, style.bg)}
      style={{ borderRadius: `0 var(--ui-radius, 12px) var(--ui-radius, 12px) 0` }}
    >
      <div className="flex items-center gap-2 mb-2">
        <Icon size={14} className="text-gray-500 shrink-0" />
        <span className="text-[11px] font-bold uppercase tracking-wider text-gray-400">
          {style.label}
        </span>
      </div>
      <h4 className="text-sm font-bold text-gray-900 mb-2">{section.title}</h4>
      <div className="text-sm text-gray-700 leading-relaxed space-y-2">
        {section.content.split('\n\n').map((paragraph, i) => (
          <p key={i} className="whitespace-pre-line">{paragraph}</p>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Module detail panel (tabbed: Learn / Challenge)
// ---------------------------------------------------------------------------

function ModuleDetail({ module, moduleProgress, onValidate, onComplete, validating, completing }: {
  module: ModuleDefinition
  moduleProgress: { completed: boolean; stars: number; attempts: number } | null
  onValidate: () => void
  onComplete: () => void
  validating: boolean
  completing: boolean
}) {
  const [tab, setTab] = useState<'learn' | 'challenge'>('learn')
  const [showTips, setShowTips] = useState(false)
  const Icon = ICON_MAP[module.icon] || BookOpen
  const completed = moduleProgress?.completed || false

  return (
    <div
      className="bg-white border-2 border-highlight/30 cert-slide-in overflow-hidden"
      style={{ borderRadius: 'var(--ui-radius, 12px)' }}
    >
      {/* Header */}
      <div className="p-6 pb-0">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div
              className="w-10 h-10 flex items-center justify-center bg-highlight/10"
              style={{ borderRadius: 'var(--ui-radius, 12px)' }}
            >
              <Icon size={22} className="text-highlight" style={{ color: 'var(--highlight-color)' }} />
            </div>
            <div>
              <h3 className="text-lg font-bold text-gray-900">
                Module {module.number}: {module.title}
              </h3>
              <p className="text-sm text-gray-500">{module.subtitle}</p>
            </div>
          </div>
          {completed && <Stars count={moduleProgress?.stars || 0} size={20} />}
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-gray-200">
          <button
            onClick={() => setTab('learn')}
            className={cn(
              'px-4 py-2.5 text-sm font-medium transition-all border-b-2 -mb-px',
              tab === 'learn'
                ? 'border-highlight text-gray-900'
                : 'border-transparent text-gray-500 hover:text-gray-700',
            )}
            style={tab === 'learn' ? { borderColor: 'var(--highlight-color)' } : undefined}
          >
            <span className="flex items-center gap-1.5">
              <BookOpen size={14} />
              Learn
            </span>
          </button>
          <button
            onClick={() => setTab('challenge')}
            className={cn(
              'px-4 py-2.5 text-sm font-medium transition-all border-b-2 -mb-px',
              tab === 'challenge'
                ? 'border-highlight text-gray-900'
                : 'border-transparent text-gray-500 hover:text-gray-700',
            )}
            style={tab === 'challenge' ? { borderColor: 'var(--highlight-color)' } : undefined}
          >
            <span className="flex items-center gap-1.5">
              <Target size={14} />
              Challenge
            </span>
          </button>
        </div>
      </div>

      {/* Tab content */}
      <div className="p-6">
        {tab === 'learn' ? (
          <div className="space-y-4">
            <p className="text-sm text-gray-700 mb-2">{module.description}</p>

            {/* Lesson sections */}
            {module.lessons.map((section, i) => (
              <LessonRenderer key={i} section={section} />
            ))}

            {/* Prompt to try the challenge */}
            <div className="flex items-center justify-between pt-4 border-t border-gray-100">
              <p className="text-sm text-gray-500">
                Ready to put this into practice?
              </p>
              <button
                onClick={() => setTab('challenge')}
                className="flex items-center gap-1.5 px-4 py-2 bg-highlight text-highlight-text text-sm font-bold hover:brightness-90 transition-all"
                style={{ borderRadius: 'var(--ui-radius, 12px)' }}
              >
                Go to Challenge
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        ) : (
          <div>
            {/* Objectives */}
            <div className="mb-5">
              <h4 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-1.5">
                <Target size={14} />
                Objectives
              </h4>
              <ul className="space-y-2">
                {module.objectives.map((obj, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <div
                      className={cn(
                        'w-5 h-5 flex items-center justify-center shrink-0 mt-0.5',
                        completed ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-400',
                      )}
                      style={{ borderRadius: 'var(--ui-radius, 12px)' }}
                    >
                      {completed ? <Check size={12} /> : <span className="text-xs">{i + 1}</span>}
                    </div>
                    <span className={cn(completed && 'text-green-800')}>{obj}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Tips */}
            <div className="mb-5">
              <button
                onClick={() => setShowTips(!showTips)}
                className="flex items-center gap-1.5 text-sm font-semibold text-gray-600 hover:text-gray-900"
              >
                <Lightbulb size={14} className="text-yellow-500" />
                Tips & Hints
                {showTips ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </button>
              {showTips && (
                <ul className="mt-2 space-y-1.5 pl-5">
                  {module.tips.map((tip, i) => (
                    <li key={i} className="text-sm text-gray-600 list-disc">{tip}</li>
                  ))}
                </ul>
              )}
            </div>

            {/* Star criteria hint */}
            <div
              className="mb-5 p-3 bg-gray-50 border border-gray-200 text-sm text-gray-600"
              style={{ borderRadius: 'var(--ui-radius, 12px)' }}
            >
              <span className="font-semibold text-gray-700">Earning stars: </span>
              Meet the minimum objectives for 1 star. Exceed them for 2-3 stars
              (e.g., more fields, more steps, more advanced node types).
            </div>

            {/* Action buttons */}
            <div className="flex items-center gap-3">
              <button
                onClick={onValidate}
                disabled={validating}
                className="flex items-center gap-2 px-4 py-2.5 border-2 border-gray-200 text-sm font-semibold text-gray-700 hover:border-highlight hover:text-highlight-text hover:bg-highlight transition-all disabled:opacity-50"
                style={{ borderRadius: 'var(--ui-radius, 12px)' }}
              >
                <FlaskConical size={16} />
                {validating ? 'Checking...' : 'Check Progress'}
              </button>
              {!completed && (
                <button
                  onClick={onComplete}
                  disabled={completing}
                  className="flex items-center gap-2 px-4 py-2.5 bg-highlight text-highlight-text text-sm font-bold hover:brightness-90 transition-all disabled:opacity-50"
                  style={{ borderRadius: 'var(--ui-radius, 12px)' }}
                >
                  <Zap size={16} />
                  {completing ? 'Completing...' : 'Complete Module'}
                </button>
              )}
            </div>

            {moduleProgress && (
              <p className="mt-3 text-xs text-gray-400">
                {moduleProgress.attempts} attempt{moduleProgress.attempts !== 1 ? 's' : ''}
                {completed && moduleProgress.completed ? ' \u00b7 Completed' : ''}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Validation results
// ---------------------------------------------------------------------------

function ValidationResults({ result, onDismiss }: { result: ValidationResult; onDismiss: () => void }) {
  return (
    <div
      className={cn(
        'border-2 p-4 cert-slide-in',
        result.passed ? 'border-green-200 bg-green-50' : 'border-amber-200 bg-amber-50',
      )}
      style={{ borderRadius: 'var(--ui-radius, 12px)' }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          {result.passed
            ? <ShieldCheck size={18} className="text-green-600" />
            : <Target size={18} className="text-amber-600" />
          }
          <span className={cn('font-semibold text-sm', result.passed ? 'text-green-800' : 'text-amber-800')}>
            {result.passed ? 'All checks passed!' : 'Some objectives remaining'}
          </span>
          {result.passed && <Stars count={result.stars} size={14} />}
        </div>
        <button onClick={onDismiss} className="text-gray-400 hover:text-gray-600">
          <X size={16} />
        </button>
      </div>
      <div className="space-y-1.5">
        {result.checks.map((check: ValidationCheck, i: number) => (
          <div key={i} className="flex items-center gap-2 text-sm">
            {check.passed
              ? <Check size={14} className="text-green-600 shrink-0" />
              : <X size={14} className="text-red-500 shrink-0" />
            }
            <span className={check.passed ? 'text-green-800' : 'text-red-700'}>{check.name}</span>
            <span className="text-gray-500 text-xs">\u2014 {check.detail}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Celebration overlay
// ---------------------------------------------------------------------------

function CelebrationOverlay({ result, onDismiss }: { result: CompletionResult; onDismiss: () => void }) {
  const levelConfig = LEVEL_CONFIG[result.level] || LEVEL_CONFIG.novice

  return (
    <div className="fixed inset-0 z-[9998] flex items-center justify-center" onClick={onDismiss}>
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 cert-fade-in" />

      {/* Confetti particles */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        {Array.from({ length: 50 }).map((_, i) => (
          <div
            key={i}
            className="cert-confetti-piece"
            style={{
              '--x': `${Math.random() * 100}vw`,
              '--delay': `${Math.random() * 2}s`,
              '--color': ['#eab308', '#ef4444', '#3b82f6', '#10b981', '#8b5cf6', '#f97316'][i % 6],
              '--size': `${6 + Math.random() * 8}px`,
              '--drift': `${-30 + Math.random() * 60}px`,
            } as React.CSSProperties}
          />
        ))}
      </div>

      {/* Content */}
      <div
        className="relative bg-white p-8 max-w-md w-full mx-4 text-center cert-pop-in"
        style={{ borderRadius: 'var(--ui-radius, 12px)' }}
        onClick={e => e.stopPropagation()}
      >
        {result.certified ? (
          <>
            <div className="cert-badge-glow mx-auto mb-4 w-20 h-20 flex items-center justify-center rounded-full"
              style={{ background: `linear-gradient(135deg, ${levelConfig.color}, var(--highlight-complement))` }}
            >
              <Award size={40} className="text-white" />
            </div>
            <h2 className="text-2xl font-bold text-gray-900 mb-2 title-shimmer">
              Vandal Workflow Architect
            </h2>
            <p className="text-gray-600 mb-4">
              You've mastered all 8 modules and earned your VWA certification.
            </p>
          </>
        ) : (
          <>
            <div className="mb-4">
              <Sparkles size={48} className="mx-auto text-highlight" style={{ color: 'var(--highlight-color)' }} />
            </div>
            <h2 className="text-2xl font-bold text-gray-900 mb-2">Module Complete!</h2>
          </>
        )}

        {/* XP earned */}
        <div className="flex items-center justify-center gap-6 my-6">
          <div className="text-center">
            <div className="text-3xl font-bold" style={{ color: 'var(--highlight-color)' }}>
              +{result.xp_earned}
            </div>
            <div className="text-xs text-gray-500 font-medium">XP EARNED</div>
          </div>
          <div className="w-px h-10 bg-gray-200" />
          <div className="text-center">
            <Stars count={result.stars} size={24} />
            <div className="text-xs text-gray-500 font-medium mt-1">STARS</div>
          </div>
        </div>

        {/* Level up */}
        {result.level_up && (
          <div
            className="flex items-center justify-center gap-2 py-2 px-4 mx-auto w-fit mb-4 cert-level-glow"
            style={{
              background: `${levelConfig.color}15`,
              border: `2px solid ${levelConfig.color}`,
              borderRadius: 'var(--ui-radius, 12px)',
            }}
          >
            <Zap size={16} style={{ color: levelConfig.color }} />
            <span className="text-sm font-bold" style={{ color: levelConfig.color }}>
              Level Up! You're now {levelConfig.label}
            </span>
          </div>
        )}

        <button
          onClick={onDismiss}
          className="mt-2 px-6 py-2.5 bg-highlight text-highlight-text text-sm font-bold hover:brightness-90 transition-all"
          style={{ borderRadius: 'var(--ui-radius, 12px)' }}
        >
          {result.certified ? 'View Certificate' : 'Continue'}
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Certified banner
// ---------------------------------------------------------------------------

function CertifiedBanner() {
  return (
    <div
      className="relative overflow-hidden p-6 text-center"
      style={{
        borderRadius: 'var(--ui-radius, 12px)',
        background: 'linear-gradient(135deg, #191919, #2d2d2d)',
      }}
    >
      {/* Shimmer sweep */}
      <div className="absolute inset-0 cert-banner-shimmer" />

      <div className="relative">
        <div className="flex items-center justify-center gap-3 mb-2">
          <Award size={28} className="text-yellow-400" />
          <h2 className="text-xl font-bold text-white title-shimmer">
            Vandal Workflow Architect
          </h2>
          <Award size={28} className="text-yellow-400" />
        </div>
        <p className="text-gray-400 text-sm">
          Certified \u00b7 All 8 modules completed \u00b7 1600 XP
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Certification() {
  const { progress, loading, validate, complete } = useCertification()
  const [activeModule, setActiveModule] = useState<string | null>(null)
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null)
  const [completionResult, setCompletionResult] = useState<CompletionResult | null>(null)
  const [validating, setValidating] = useState(false)
  const [completing, setCompleting] = useState(false)
  const detailRef = useRef<HTMLDivElement>(null)

  const level = progress?.level || 'novice'
  const levelConfig = LEVEL_CONFIG[level] || LEVEL_CONFIG.novice
  const totalXp = progress?.total_xp || 0
  const completedCount = useMemo(() => {
    if (!progress) return 0
    return Object.values(progress.modules).filter(m => m.completed).length
  }, [progress])

  // Find next level threshold
  const currentLevelIdx = LEVEL_THRESHOLDS.findIndex(l => l.name === level)
  const nextLevel = LEVEL_THRESHOLDS[currentLevelIdx + 1] || LEVEL_THRESHOLDS[LEVEL_THRESHOLDS.length - 1]
  const prevLevel = LEVEL_THRESHOLDS[currentLevelIdx] || LEVEL_THRESHOLDS[0]

  const overallPct = (totalXp / TOTAL_XP) * 100

  const isModuleLocked = (moduleId: string): boolean => {
    const idx = MODULES.findIndex(m => m.id === moduleId)
    if (idx === 0) return false
    const prevModule = MODULES[idx - 1]
    return !progress?.modules[prevModule.id]?.completed
  }

  const handleValidate = async (moduleId: string) => {
    setValidating(true)
    setValidationResult(null)
    try {
      const result = await validate(moduleId)
      setValidationResult(result)
    } finally {
      setValidating(false)
    }
  }

  const handleComplete = async (moduleId: string) => {
    setCompleting(true)
    try {
      const result = await complete(moduleId)
      setCompletionResult(result)
    } catch {
      // Validation failed — trigger validate to show what's missing
      await handleValidate(moduleId)
    } finally {
      setCompleting(false)
    }
  }

  const handleModuleClick = (moduleId: string) => {
    if (isModuleLocked(moduleId)) return
    setActiveModule(activeModule === moduleId ? null : moduleId)
    setValidationResult(null)
    // Scroll to detail after render
    setTimeout(() => detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 100)
  }

  if (loading) {
    return (
      <PageLayout>
        <div className="p-6 max-w-5xl mx-auto">
          <div className="text-gray-500 text-sm">Loading certification progress...</div>
        </div>
      </PageLayout>
    )
  }

  const activeModuleDef = MODULES.find(m => m.id === activeModule)

  return (
    <PageLayout>
      <div className="p-6 max-w-5xl mx-auto space-y-8">

        {/* Hero Section */}
        {progress?.certified ? (
          <CertifiedBanner />
        ) : (
          <div
            className="flex flex-col sm:flex-row items-center gap-8 p-6 bg-white border border-gray-200"
            style={{ borderRadius: 'var(--ui-radius, 12px)' }}
          >
            {/* Progress Ring */}
            <div className="relative shrink-0">
              <ProgressRing percentage={overallPct} color={levelConfig.color} />
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-2xl font-bold text-gray-900">{Math.round(overallPct)}%</span>
                <span
                  className="text-xs font-bold uppercase tracking-wider"
                  style={{ color: levelConfig.color }}
                >
                  {levelConfig.label}
                </span>
              </div>
            </div>

            {/* Stats */}
            <div className="flex-1 w-full">
              <h1 className="text-2xl font-bold text-gray-900 mb-1">
                Vandal Workflow Architect
              </h1>
              <p className="text-sm text-gray-500 mb-5">
                Master all 8 modules to earn your VWA certification
              </p>

              {/* XP bar */}
              <XPBar
                current={totalXp}
                nextThreshold={nextLevel.xp}
                prevThreshold={prevLevel.xp}
                nextLevel={nextLevel.name}
              />

              {/* Stat pills */}
              <div className="flex flex-wrap gap-3 mt-4">
                <div
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-50 border border-gray-200 text-sm"
                  style={{ borderRadius: 'var(--ui-radius, 12px)' }}
                >
                  <Award size={14} className="text-highlight" style={{ color: 'var(--highlight-color)' }} />
                  <span className="font-semibold text-gray-900">{completedCount}</span>
                  <span className="text-gray-500">/ 8 modules</span>
                </div>
                <div
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-50 border border-gray-200 text-sm"
                  style={{ borderRadius: 'var(--ui-radius, 12px)' }}
                >
                  <Zap size={14} className="text-highlight" style={{ color: 'var(--highlight-color)' }} />
                  <span className="font-semibold text-gray-900">{totalXp}</span>
                  <span className="text-gray-500">/ {TOTAL_XP} XP</span>
                </div>
                {(progress?.streak_days || 0) > 0 && (
                  <div
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-orange-50 border border-orange-200 text-sm"
                    style={{ borderRadius: 'var(--ui-radius, 12px)' }}
                  >
                    <Flame size={14} className="text-orange-500" />
                    <span className="font-semibold text-orange-700">{progress?.streak_days}</span>
                    <span className="text-orange-600">day streak</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Module Grid */}
        <div>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Training Modules</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {MODULES.map(module => {
              const modProgress = progress?.modules[module.id]
              return (
                <ModuleCard
                  key={module.id}
                  module={module}
                  completed={modProgress?.completed || false}
                  stars={modProgress?.stars || 0}
                  locked={isModuleLocked(module.id)}
                  active={activeModule === module.id}
                  onClick={() => handleModuleClick(module.id)}
                />
              )
            })}
          </div>
        </div>

        {/* Active Module Detail */}
        {activeModuleDef && (
          <div ref={detailRef} className="space-y-4">
            <ModuleDetail
              module={activeModuleDef}
              moduleProgress={progress?.modules[activeModuleDef.id] ? {
                completed: progress.modules[activeModuleDef.id].completed,
                stars: progress.modules[activeModuleDef.id].stars,
                attempts: progress.modules[activeModuleDef.id].attempts,
              } : null}
              onValidate={() => handleValidate(activeModuleDef.id)}
              onComplete={() => handleComplete(activeModuleDef.id)}
              validating={validating}
              completing={completing}
            />

            {validationResult && (
              <ValidationResults result={validationResult} onDismiss={() => setValidationResult(null)} />
            )}
          </div>
        )}

        {/* Level Map */}
        <div
          className="p-5 bg-white border border-gray-200"
          style={{ borderRadius: 'var(--ui-radius, 12px)' }}
        >
          <h3 className="text-sm font-semibold text-gray-900 mb-4 flex items-center gap-1.5">
            <Cog size={14} />
            Level Progression
          </h3>
          <div className="flex items-center gap-1">
            {LEVEL_THRESHOLDS.map((lvl, i) => {
              const config = LEVEL_CONFIG[lvl.name]
              const reached = totalXp >= lvl.xp
              const isCurrent = level === lvl.name
              return (
                <div key={lvl.name} className="flex-1 flex flex-col items-center">
                  <div
                    className={cn(
                      'w-full h-2 transition-all duration-500',
                      i === 0 && 'rounded-l-full',
                      i === LEVEL_THRESHOLDS.length - 1 && 'rounded-r-full',
                    )}
                    style={{
                      background: reached ? config.color : '#e5e7eb',
                    }}
                  />
                  <div
                    className={cn(
                      'mt-2 text-[10px] font-medium text-center transition-all',
                      isCurrent ? 'font-bold' : reached ? '' : 'text-gray-400',
                    )}
                    style={reached ? { color: config.color } : undefined}
                  >
                    {config.label}
                  </div>
                  {isCurrent && (
                    <div
                      className="w-1.5 h-1.5 rounded-full mt-0.5"
                      style={{ background: config.color }}
                    />
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Celebration overlay */}
      {completionResult && (
        <CelebrationOverlay result={completionResult} onDismiss={() => setCompletionResult(null)} />
      )}
    </PageLayout>
  )
}
