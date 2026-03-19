import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import {
  Award,
  Cog,
  Flame,
  ShieldCheck,
  Star,
  Target,
  X,
  Zap,
} from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useCertification } from '../hooks/useCertification'
import { useToast } from '../contexts/ToastContext'
import { cn } from '../lib/cn'
import type { ModuleDefinition, ValidationResult, CompletionResult, ValidationCheck, CertExercise } from '../types/certification'

// Components
import { CertifiedBanner } from '../components/certification/CertifiedBanner'
import { CelebrationOverlay } from '../components/certification/CelebrationOverlay'
import { ModuleDetail } from '../components/certification/ModuleDetail'
import { JourneyMap } from '../components/certification/JourneyMap'
import { LEVEL_CONFIG, LEVEL_THRESHOLDS, TOTAL_XP, TIERS } from '../components/certification/constants'

// ---------------------------------------------------------------------------
// Module definitions
// ---------------------------------------------------------------------------

export const MODULES: ModuleDefinition[] = [
  {
    id: 'ai_literacy',
    number: 0,
    title: 'AI Literacy',
    subtitle: 'Understanding AI for Research Administration',
    description: 'Welcome to the Vandal Workflow Architect certification. By the end of this program, you\'ll earn an official VWA credential recognizing your ability to design and deploy AI-powered workflows for research administration. This first module builds your foundation — what AI actually is, what it\'s good and bad at, and how it applies to your work. No technical skills required yet.',
    objectives: [
      'Understand what an LLM is and how it generates text',
      'Learn the key terms you\'ll encounter throughout this certification',
      'Reflect on your own experience and comfort level with AI tools',
    ],
    tips: [
      'There are no wrong answers on the self-assessment — it\'s for your own reflection',
      'The key terms in this module will come up repeatedly in later modules',
      'If you\'re skeptical about AI, that\'s healthy — this module is designed to give you an honest picture',
    ],
    lessons: [
      {
        title: 'What is an LLM, really?',
        content: 'A Large Language Model (LLM) is not thinking. It is not sentient. It does not understand your documents the way you do.\n\nAn LLM is a sophisticated pattern-completion engine trained on vast amounts of text. When you give it a prompt, it predicts the most likely next words based on patterns it learned during training. This is both why it\'s capable and why it makes mistakes.\n\nIt\'s capable because human language follows patterns. A grant proposal has a predictable structure: PI name, institution, budget, aims. The LLM has seen thousands of similar documents and can reliably identify these patterns.\n\nIt makes mistakes because pattern-matching is not understanding. The LLM doesn\'t know what a budget is — it knows that numbers near the word "budget" are likely dollar amounts. When the pattern breaks (unusual formatting, ambiguous language), the LLM may confidently produce wrong answers.',
        variant: 'concept',
        diagram: 'how-llm-works',
        knowledgeCheck: {
          question: 'An LLM generates text by...',
          options: [
            { text: 'Thinking through the problem logically, like a human would', correct: false, explanation: 'LLMs don\'t "think" — they predict patterns based on training data.' },
            { text: 'Predicting the most likely next words based on patterns from training data', correct: true, explanation: 'Correct! LLMs are pattern-completion engines trained on vast text.' },
            { text: 'Looking up answers in a database of facts', correct: false, explanation: 'LLMs don\'t have a database — they learned patterns from training text.' },
            { text: 'Running a search engine to find relevant information', correct: false, explanation: 'LLMs generate text from learned patterns, not from searching the internet.' },
          ],
        },
      },
      {
        title: 'Key terms you will encounter',
        content: 'LLM (Large Language Model) \u2014 The AI engine that processes text. Examples: GPT-4, Claude, Gemini. Think of it as a very sophisticated autocomplete that can follow complex instructions.\n\nPrompt \u2014 The instructions you give to an LLM. A good prompt is specific and provides context. "Extract the PI name" is a prompt. The quality of your prompt directly affects the quality of the output.\n\nHallucination \u2014 When an LLM generates information that sounds plausible but is factually wrong. This is the #1 risk in research administration. An LLM might confidently report a budget of $500,000 when the document says $50,000.\n\nStructured Output \u2014 Forcing the LLM to return data in a specific format (like JSON with defined fields) instead of free-form text. This is how Vandalizer ensures consistent, machine-readable results.\n\nToken \u2014 The unit of text an LLM processes. Roughly 1 token = 3/4 of a word. Relevant because models have token limits that affect how much document text they can process at once.\n\nRAG (Retrieval-Augmented Generation) \u2014 A technique where the LLM is given relevant excerpts from your actual documents before generating a response. This grounds the output in real data rather than the LLM\'s training data.',
        variant: 'key-terms',
      },
      {
        title: 'What AI is genuinely good at',
        content: 'AI excels at tasks that involve pattern recognition across large volumes of text:\n\n\u2022 **Extracting specific information** from long documents \u2014 Finding the PI name, budget, and project period in a 50-page proposal.\n\u2022 **Summarizing** \u2014 Condensing a progress report into key findings and milestones.\n\u2022 **Comparing across documents** \u2014 Identifying differences between two versions of a budget justification.\n\u2022 **Drafting routine text** \u2014 Generating first drafts of compliance summaries or progress report templates.\n\u2022 **Processing many documents consistently** \u2014 Applying the same extraction to 200 proposals and getting results in the same format every time.\n\nThe common thread: these are tasks where a human would be doing repetitive reading and data entry. AI handles the volume; you handle the judgment.',
        variant: 'concept',
      },
      {
        title: 'What AI is genuinely bad at',
        content: 'Honesty about AI\'s limitations is essential for responsible use in research administration:\n\n\u2022 **Judgment calls requiring institutional knowledge** \u2014 AI doesn\'t know your university\'s internal policies, political dynamics, or historical context.\n\u2022 **Catching its own mistakes** \u2014 An LLM cannot reliably self-check. If it extracts the wrong budget figure, it won\'t flag the error. That\'s your job.\n\u2022 **Math** \u2014 LLMs frequently make arithmetic errors. Never trust an LLM to add up budget line items. Use code execution nodes for calculations.\n\u2022 **Novel or unusual document formats** \u2014 If a document doesn\'t follow standard patterns (hand-written notes, unusual layouts, scanned images with poor OCR), extraction quality drops significantly.\n\u2022 **Replacing professional judgment on compliance** \u2014 AI can flag potential issues, but determining whether a proposal actually meets regulatory requirements requires your expertise.\n\nThe pattern: AI is a powerful first-pass tool. It does the reading; you do the thinking.',
        variant: 'insight',
        knowledgeCheck: {
          question: 'Which task is AI worst at?',
          options: [
            { text: 'Extracting PI names from grant proposals', correct: false, explanation: 'This is actually a strong suit for AI \u2014 it\'s pattern-based extraction from structured documents.' },
            { text: 'Summarizing progress reports', correct: false, explanation: 'Summarization is one of AI\'s strengths \u2014 it\'s good at condensing text.' },
            { text: 'Making judgment calls that require institutional knowledge', correct: true, explanation: 'Correct! AI doesn\'t know your institution\'s policies, politics, or historical context. That requires your expertise.' },
            { text: 'Processing 200 documents in the same format', correct: false, explanation: 'Batch processing with consistent format is ideal for AI \u2014 it handles repetition well.' },
          ],
        },
      },
      {
        title: 'AI for research administration',
        content: 'Here\'s what AI-assisted research administration looks like in practice:\n\n\u2022 **Proposal intake** \u2014 Upload 30 new proposals. A workflow extracts PI name, agency, budget, and key dates from each one in minutes instead of hours.\n\u2022 **Progress report processing** \u2014 Extract accomplishments, publications, and expenditures from annual reports. Flag any that are missing required sections.\n\u2022 **Compliance pre-screening** \u2014 Check proposals against a list of required elements (human subjects approval, data management plan, budget justification) and flag gaps.\n\u2022 **Subaward review** \u2014 Extract parties, amounts, and terms from subaward agreements. Compare against institutional templates.\n\nThe pattern in every case: AI does the first pass of extraction, you do the second pass of verification and judgment. The AI handles volume and consistency. You bring expertise and accountability.',
        variant: 'concept',
        diagram: 'ai-human-pattern',
      },
      {
        title: 'From chatbot to structured pipeline',
        content: 'You may have used ChatGPT or Copilot to ask questions about a document. That works for one-off questions, but it fails for professional research administration work:\n\n\u2022 **Inconsistent format** \u2014 Ask the same question twice and you\'ll get differently structured answers.\n\u2022 **No audit trail** \u2014 There\'s no record of what was extracted, when, or from which document.\n\u2022 **Can\'t scale** \u2014 You can\'t paste 200 proposals into a chatbot one at a time.\n\u2022 **No verification** \u2014 There\'s no systematic way to check if the answers are correct.\n\nWorkflows solve all of these problems. A workflow defines exactly what to extract, produces consistent structured output, maintains a complete audit trail, runs across hundreds of documents, and can be validated for accuracy.\n\nThis is the bridge from "AI as a toy" to "AI as a professional tool." Over the next 10 modules, you\'ll learn to decompose your real processes, build workflows that handle them, validate those workflows for accuracy, and deploy them at scale. When you complete all 11 modules, you\'ll earn your Vandal Workflow Architect certification \u2014 a credential that says you can turn any document-heavy process into a reliable, AI-powered pipeline.',
        variant: 'insight',
      },
    ],
    xp: 50,
    icon: 'Lightbulb',
    estimatedMinutes: 10,
  },
  {
    id: 'foundations',
    number: 1,
    title: 'Foundations',
    subtitle: 'Documents In, Intelligence Out',
    description: 'Learn the basics of workflows using a sample NSF proposal from Dr. Sarah Chen. Click Set Up Lab to load it, then build your first extraction workflow.',
    objectives: [
      'Add the sample NSF proposal to your workspace',
      'Create a workflow with an Extraction step and 5 fields',
      'Run the workflow and verify extracted values',
    ],
    tips: [
      'The sample NSF proposal contains clearly labeled fields like PI Name, Institution, and Total Budget',
      'Use clear, descriptive field names in your SearchSet that match the document labels',
      'After running, check that PI Name = Sarah Chen and Total Budget = $485,000',
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
        content: 'When you upload a document, Vandalizer processes it through several stages:\n\n1. **Text extraction** \u2014 The raw text is pulled from PDFs, DOCX, XLSX, and HTML files using specialized readers.\n2. **Chunking** \u2014 The text is split into overlapping segments for semantic search.\n3. **Embedding** \u2014 Each chunk is embedded into ChromaDB, a vector database, so it can be searched semantically.\n\nWhen a workflow runs an Extraction step, the LLM receives the full document text and your SearchSet fields, and returns structured JSON with the extracted values.',
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
    estimatedMinutes: 15,
  },
  {
    id: 'process_mapping',
    number: 2,
    title: 'Thinking in Workflows',
    subtitle: 'See Your Work as Automatable Processes',
    description: 'Before you can build a workflow, you need to see your work differently. This module teaches you to recognize the repeatable processes hiding in your daily tasks, identify which parts are suitable for AI, and which parts need your expertise.',
    objectives: [
      'Recognize repeatable processes in your research administration work',
      'Identify which parts of a process are AI-suitable vs. human-judgment',
      'Apply the process decomposition framework to a real task from your work',
    ],
    tips: [
      'Think about the tasks you do every week that follow the same pattern',
      'The best workflow candidates are tasks where you spend most of your time reading and re-typing',
      'Don\'t try to automate everything \u2014 the goal is to automate the tedious parts so you can focus on the important parts',
    ],
    lessons: [
      {
        title: 'Your work is already a workflow',
        content: 'You already run workflows every day \u2014 you just run them in your head.\n\nWhen you process an incoming proposal, you probably follow steps like these:\n1. Open the document and skim for key details.\n2. Find the PI name, institution, budget, and project dates.\n3. Check whether required sections are present.\n4. Enter the data into a spreadsheet or system.\n5. Flag anything unusual for follow-up.\n\nThat\'s a workflow. You do the same steps in roughly the same order every time. The difference between that mental process and a Vandalizer workflow is that one runs in your head (inconsistently, one document at a time) and the other runs on a computer (consistently, across hundreds of documents).\n\nThe first step toward automation is recognizing these patterns in your own work.',
        variant: 'concept',
      },
      {
        title: 'The process decomposition framework',
        content: 'Input \u2014 What triggers this process? Usually a document arriving: a proposal, a report, a subaward agreement, a budget justification.\n\nSteps \u2014 The discrete actions you take, in order. Each step has a clear purpose: "find the PI name," "check the budget," "write a summary."\n\nDecision Points \u2014 Where you apply judgment: "Is this budget reasonable?" "Does this meet compliance requirements?" These are where human expertise is essential.\n\nHandoffs \u2014 Where work passes between people: "Send to compliance officer for review," "Return to PI for corrections."\n\nOutput \u2014 What\'s produced at the end: a completed form, a summary report, a recommendation, data entered into a system.\n\nEvery process in your office can be described using these five elements. Once you can identify them, you can start deciding which steps to automate.',
        variant: 'key-terms',
      },
      {
        title: 'Finding the repetition',
        content: 'The best candidates for workflows are tasks that share three properties:\n\n1. **You do them repeatedly** \u2014 not once, but dozens or hundreds of times. Processing proposals, reviewing progress reports, checking compliance documents.\n\n2. **You follow the same steps each time** \u2014 you look for the same information, in the same kinds of documents, and produce the same kind of output.\n\n3. **Most of the time is spent reading, not thinking** \u2014 you spend 80% of your time finding information in documents and 20% making decisions about it.\n\nHere\'s a quick test: could you write step-by-step instructions for a new hire to do this task? If yes, it\'s a workflow. If the instructions would be "use your judgment," that specific step stays human.\n\nCommon research admin processes that pass this test:\n\u2022 Processing incoming proposals (extracting key fields)\n\u2022 Reviewing progress reports (checking completeness)\n\u2022 Pre-screening for compliance (finding required elements)\n\u2022 Summarizing subaward terms (extracting parties and obligations)\n\u2022 Preparing data for reports (gathering numbers from multiple documents)',
        variant: 'concept',
        knowledgeCheck: {
          question: 'What makes a process a good candidate for AI automation?',
          options: [
            { text: 'It requires deep institutional knowledge and professional judgment', correct: false, explanation: 'Tasks requiring judgment should stay with humans \u2014 AI handles the repetitive reading part.' },
            { text: 'It\'s repetitive, document-based, and most time is spent reading rather than thinking', correct: true, explanation: 'Correct! The best AI candidates are repetitive tasks where you spend most time extracting information from documents.' },
            { text: 'It only happens once or twice a year', correct: false, explanation: 'Rare tasks don\'t benefit much from automation \u2014 the setup cost outweighs the time saved.' },
            { text: 'It involves making complex financial decisions', correct: false, explanation: 'Complex decisions require human expertise. AI is better at the extraction that feeds into those decisions.' },
          ],
        },
      },
      {
        title: 'The AI suitability test',
        content: 'Not every step in your process should be automated. Here\'s a practical framework:\n\n**AI-suitable** (automate these):\n\u2022 Reading a document and finding specific information \u2192 Extraction\n\u2022 Summarizing or paraphrasing document content \u2192 Prompt\n\u2022 Comparing information across documents \u2192 Prompt\n\u2022 Reformatting data from one structure to another \u2192 Formatter\n\u2022 Drafting routine text based on extracted data \u2192 Prompt\n\n**Use code, not AI**:\n\u2022 Adding up numbers or computing percentages \u2192 Code Execution\n\u2022 Date calculations or comparisons \u2192 Code Execution\n\u2022 Applying deterministic rules ("if budget > $500K, flag for review") \u2192 Code Execution\n\n**Keep human**:\n\u2022 Deciding whether something meets a policy requirement\n\u2022 Interpreting ambiguous or unusual situations\n\u2022 Making recommendations that require institutional context\n\u2022 Anything where a mistake has serious consequences and can\'t be easily caught\n\nThe pattern: AI reads and extracts. Code computes. Humans judge.',
        variant: 'insight',
        diagram: 'ai-suitability',
      },
      {
        title: 'Walkthrough: Mapping a real process',
        content: 'Let\'s decompose "processing incoming proposals" step by step:\n\n1. **Receive the proposal document** (PDF) \u2192 Input: this is your workflow trigger.\n\n2. **Find PI name, institution, budget, project dates, agency** \u2192 AI-suitable: this is reading and extracting. Map to an Extraction step.\n\n3. **Check whether required sections are present** (data management plan, budget justification, biosketches) \u2192 AI-suitable: checking for presence of sections. Map to a Prompt step.\n\n4. **Verify the budget adds up** \u2192 Use code: map to a Code Execution step that sums extracted line items.\n\n5. **Decide whether to flag for compliance review** \u2192 Keep human: this requires institutional judgment. This is where your workflow ends and your review begins.\n\n6. **Enter data into your tracking system** \u2192 The workflow\'s structured output makes this copy-paste or even automated via API.\n\nResult: a 3-step workflow (Extract \u2192 Check sections \u2192 Verify budget) that does 70% of the work, leaving you to do the 30% that requires your expertise.',
        variant: 'walkthrough',
      },
      {
        title: 'Common processes that become workflows',
        content: 'Here are the most common research administration processes and how they map to workflows:\n\n\u2022 **Proposal intake** \u2014 Extract key fields, check completeness, flag gaps. 3-4 steps.\n\u2022 **Progress report review** \u2014 Extract accomplishments, publications, expenditures. Summarize and compare to milestones. 3 steps.\n\u2022 **Compliance pre-screening** \u2014 Extract required elements, check against a compliance checklist, produce a gap report. 3-4 steps.\n\u2022 **Budget review** \u2014 Extract line items, compute totals, compare to limits, produce a summary. 4 steps.\n\u2022 **Subaward processing** \u2014 Extract parties, amounts, terms, deliverables. Flag deviations from templates. 3 steps.\n\u2022 **Award closeout** \u2014 Gather final expenditures, publications, and deliverables from multiple documents. 4-5 steps.\n\nNotice the pattern: every workflow starts with extraction (getting data out of documents) and ends with either a human review point or a produced deliverable. The middle steps are where analysis, comparison, and computation happen.',
        variant: 'concept',
      },
    ],
    xp: 100,
    icon: 'Search',
    estimatedMinutes: 15,
  },
  {
    id: 'workflow_design',
    number: 3,
    title: 'Workflow Design',
    subtitle: 'From Process Map to Pipeline Architecture',
    description: 'Now that you can decompose a process, learn how to translate it into a specific workflow architecture. Which task types fit which steps? How should data flow? Where do humans stay in the loop?',
    objectives: [
      'Map process steps to specific Vandalizer task types',
      'Understand the extract-reason-deliver pattern',
      'Design workflows that support human review, not replace it',
    ],
    tips: [
      'Start simple \u2014 a 2-3 step workflow that works is better than a 10-step workflow that doesn\'t',
      'Design your output for the person who will review it, not for the computer',
      'When in doubt about step granularity, split \u2014 it\'s easier to combine steps later than to debug one giant step',
    ],
    lessons: [
      {
        title: 'From process map to workflow architecture',
        content: 'In the previous module, you decomposed a process into steps and identified which are AI-suitable. Now you need to translate each step into a specific task type in Vandalizer.\n\nThe mapping is straightforward:\n\u2022 "Find information in a document" \u2192 Extraction task with a SearchSet\n\u2022 "Analyze or summarize the extracted data" \u2192 Prompt task\n\u2022 "Compute, total, or apply rules" \u2192 Code Execution task\n\u2022 "Check a document for specific sections or elements" \u2192 Prompt task\n\u2022 "Produce a formatted report or export" \u2192 Document Renderer or Data Export\n\u2022 "Compare this document to another" \u2192 Add Document + Prompt task\n\nThe key insight: you\'re not starting from scratch asking "what can this tool do?" You\'re starting from your process and asking "which tool handles this step?"',
        variant: 'concept',
      },
      {
        title: 'Key design decisions',
        content: 'Step granularity \u2014 How many steps should your workflow have? Each step should do one clear thing. If you can\'t describe a step\'s purpose in one sentence, split it.\n\nTask type selection \u2014 Choose the simplest task type that gets the job done. If you need structured data from a document, use Extraction \u2014 don\'t write a Prompt asking the LLM to produce JSON.\n\nData flow \u2014 Each step receives the previous step\'s output. Design your steps so the output of one naturally feeds the next. Extraction produces JSON; a Prompt can analyze that JSON; a Renderer can format the analysis.\n\nHuman checkpoints \u2014 Decide where a human should review before the workflow continues. In most research admin workflows, the answer is: review after the final output, not after every step.\n\nError tolerance \u2014 What happens if the LLM extracts a field incorrectly? Design your workflow so errors are visible in the output, not hidden. Show source data alongside conclusions.',
        variant: 'key-terms',
      },
      {
        title: 'The extract-reason-deliver pattern',
        content: 'The most common and most effective workflow pattern in research administration has three phases:\n\n1. **Extract** \u2014 Pull structured data from the document. This is your Extraction step with a well-designed SearchSet. The output is clean, consistent JSON.\n\n2. **Reason** \u2014 Analyze the extracted data. This might be a Prompt step that summarizes findings, a Code Execution step that computes totals, or both. The output is analysis or computed results.\n\n3. **Deliver** \u2014 Produce something useful. A formatted report, a CSV export, a compliance checklist, or structured data ready for your tracking system.\n\nThis pattern works because it separates concerns. If your final report is wrong, you can check: did the extraction get the right data? (Check step 1\'s output.) Did the analysis interpret it correctly? (Check step 2.) You can fix the broken step without rebuilding the whole workflow.',
        variant: 'concept',
        diagram: 'extract-reason-deliver',
        knowledgeCheck: {
          question: 'The Extract-Reason-Deliver pattern starts with...',
          options: [
            { text: 'Analyzing the data to draw conclusions', correct: false, explanation: 'Analysis is the "Reason" phase \u2014 it comes after extraction.' },
            { text: 'Producing a formatted report', correct: false, explanation: 'Report generation is the "Deliver" phase \u2014 it comes last.' },
            { text: 'Pulling structured data from the document', correct: true, explanation: 'Correct! Extract first, reason second, deliver third. Always start by getting clean data out of the document.' },
            { text: 'Asking the LLM to do everything in one prompt', correct: false, explanation: 'One-shot prompting is the opposite of this pattern \u2014 it separates extraction from analysis from delivery.' },
          ],
        },
      },
      {
        title: 'Designing for your reviewer',
        content: 'Here\'s a truth about AI in research administration: someone will always review the output. Maybe it\'s you, maybe it\'s a compliance officer, maybe it\'s a PI. Your workflow should make that review easy and efficient.\n\nDesign principles for reviewable output:\n\n\u2022 **Show your sources** \u2014 When the workflow extracts a budget figure, the output should make it easy to verify against the source document.\n\u2022 **Flag uncertainty** \u2014 If a field couldn\'t be found or the value seems unusual, the output should say so.\n\u2022 **Structure for scanning** \u2014 The reviewer should be able to scan the output in 30 seconds and know if everything looks right.\n\u2022 **Separate data from analysis** \u2014 Show the raw extracted data first, then the analysis or recommendations.\n\nThe workflow\'s job is not to eliminate review. It\'s to make review fast and focused.',
        variant: 'insight',
      },
      {
        title: 'Walkthrough: Designing a compliance review pipeline',
        content: 'Process: "Check whether a grant proposal includes all required compliance elements."\n\n**Step 1** \u2014 Decompose the process:\n\u2022 Read the proposal and identify which compliance sections are present\n\u2022 Extract specific compliance data (human subjects, data management, conflict of interest)\n\u2022 Compare against the required elements checklist\n\u2022 Produce a gap report showing what\'s present and what\'s missing\n\n**Step 2** \u2014 Map to task types:\n\u2022 "Read and extract compliance data" \u2192 Extraction task\n\u2022 "Compare against checklist" \u2192 Prompt task\n\u2022 "Produce gap report" \u2192 Document Renderer task\n\n**Step 3** \u2014 Design data flow:\n\u2022 Step 1 output: JSON with compliance field values (or "not found")\n\u2022 Step 2 input: that JSON. Output: analysis text with present/missing/incomplete categories\n\u2022 Step 3 input: analysis text. Output: formatted compliance checklist document\n\nResult: A 3-step workflow. Upload a proposal, click Run, download a compliance checklist.',
        variant: 'walkthrough',
      },
      {
        title: 'When to split, when to combine',
        content: 'A common question: should this be one step or two?\n\n**Split into separate steps when:**\n\u2022 You\'d want to check the intermediate output\n\u2022 The operations are different types \u2014 extraction and analysis are different skills\n\u2022 You might reuse one part\n\u2022 Debugging would be easier\n\n**Combine into one step when:**\n\u2022 The operations are tightly coupled\n\u2022 The intermediate output isn\'t useful on its own\n\u2022 The combined prompt is simple and focused\n\nRule of thumb: start with more steps. You can always combine later once you know the workflow works. But splitting a monolithic step that\'s producing bad output is much harder than combining two steps that work well individually.',
        variant: 'insight',
        diagram: 'step-granularity',
      },
    ],
    xp: 100,
    icon: 'Compass',
    estimatedMinutes: 15,
  },
  {
    id: 'extraction_engine',
    number: 4,
    title: 'Extraction Engine',
    subtitle: 'Master the Extraction Pipeline',
    description: 'Build a comprehensive 20+ field extraction using a sample NIH R01 proposal from Dr. James Park. The document has budget breakdowns, key personnel, and specific aims to extract.',
    objectives: [
      'Add the sample NIH R01 proposal to your workspace',
      'Create a SearchSet with 15+ fields covering all document sections',
      'Extract budget categories, personnel, aims, and compliance fields',
    ],
    tips: [
      'The NIH R01 has clearly structured sections: budget, key personnel, specific aims, vertebrate animals',
      'Use enum_values to constrain fields like Human Subjects (Yes/No) and Clinical Trial (Yes/No)',
      'Mark fields like Co-Investigator as optional since there may be multiple',
    ],
    lessons: [
      {
        title: 'One-pass vs. two-pass extraction',
        content: 'Vandalizer offers two extraction strategies:\n\n**One-pass extraction** sends the document and field definitions to the LLM in a single call. It\'s faster and cheaper, but can miss nuances in complex documents.\n\n**Two-pass extraction** (the default) works in two stages:\n\u2022 Pass 1: The LLM creates a draft extraction, thinking through each field.\n\u2022 Pass 2: A second LLM call refines the draft, using structured output to produce clean, validated JSON.\n\nThe two-pass approach is more accurate because the second pass can correct mistakes from the first, and the structured output format prevents formatting errors.',
        variant: 'concept',
      },
      {
        title: 'Key terms',
        content: 'Structured Output \u2014 The LLM is constrained to return data matching a specific schema (built from your SearchSet fields as a dynamic Pydantic model). This prevents formatting errors and hallucinated fields.\n\nThinking Mode \u2014 When enabled, the LLM reasons step-by-step before answering. Pass 1 uses thinking for accuracy; Pass 2 disables it for speed.\n\nConsensus Repetition \u2014 An optional mode that runs extraction 3 times in parallel and uses majority voting to resolve disagreements. 3x the cost, but highest accuracy for critical fields.\n\nChunking \u2014 When you have many fields (20+), the extraction can be split into smaller batches to avoid overwhelming the LLM\'s context window.',
        variant: 'key-terms',
      },
      {
        title: 'Configuring fields for accuracy',
        content: 'The way you configure your SearchSet fields directly impacts extraction quality:\n\n**Field names** should be specific and unambiguous. "PI Name" is better than "Name". "Total Budget (USD)" is better than "Budget".\n\n**Enum values** constrain a field to a set of allowed options. For a field like "Document Type", you might set enum values to ["Grant Proposal", "Progress Report", "Budget Justification"]. This prevents the LLM from inventing categories.\n\n**Optional fields** should be marked as such. If a field like "Co-PI" won\'t appear in every document, marking it optional tells the extraction engine not to hallucinate a value when one doesn\'t exist.\n\n**Field descriptions** (in the title/searchphrase) give the LLM additional context about what to look for.',
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
    estimatedMinutes: 20,
  },
  {
    id: 'multi_step',
    number: 5,
    title: 'Multi-Step Workflows',
    subtitle: 'Chain Steps Together',
    description: 'Build a multi-step pipeline using a sample subaward agreement between University of Idaho and Boise State. Extract parties and terms, analyze obligations, then format a compliance summary.',
    objectives: [
      'Add the sample subaward agreement to your workspace',
      'Build a 3-step workflow: Extraction + Prompt + Formatter',
      'Verify the pipeline chains correctly from extraction to formatted report',
    ],
    tips: [
      'The subaward has two parties (UI and BSU), financial terms, deliverables, and compliance requirements',
      'Use the Prompt step to analyze obligations and flag key deadlines',
      'The Formatter step should produce a clean compliance summary from the analysis',
    ],
    lessons: [
      {
        title: 'How steps chain together',
        content: 'A multi-step workflow forms a pipeline where each step\'s output becomes the next step\'s input. The workflow engine executes steps in order (technically, in topological order of a directed acyclic graph, or DAG).\n\nFor example, a 3-step workflow might work like this:\n\u2022 Step 1 (Extraction): Pulls structured fields from the document \u2192 outputs JSON.\n\u2022 Step 2 (Prompt): Receives that JSON and asks the LLM to analyze it \u2192 outputs analysis text.\n\u2022 Step 3 (Format): Takes the analysis and formats it into a clean report \u2192 outputs final document.\n\nEach step can see the output of the step before it, creating a chain of increasingly refined output.',
        variant: 'concept',
      },
      {
        title: 'Key terms',
        content: 'Input Source \u2014 Controls what data a step receives. Options: "step_input" (previous step\'s output), "select_document" (a specific document), "workflow_documents" (all selected documents).\n\nPrompt Node \u2014 Sends data to the LLM with a custom prompt. Great for analysis, summarization, comparison, or decision-making based on extracted data.\n\nFormat Node \u2014 Transforms structured data into formatted text (markdown, plain text, etc.). Use it to turn raw JSON into human-readable reports.\n\nPost-process Prompt \u2014 An optional final LLM call on any node\'s output. Use it to clean up or reformat results without adding a separate step.',
        variant: 'key-terms',
      },
      {
        title: 'The Prompt node: reasoning over data',
        content: 'The Prompt node is one of the most powerful tools in your workflow. It sends the previous step\'s output to the LLM along with your custom prompt, and returns the LLM\'s response.\n\nUse it to:\n\u2022 Summarize extracted data\n\u2022 Compare and analyze\n\u2022 Generate recommendations\n\u2022 Transform formats\n\nThe key insight is that extraction gives you structured data, and prompts let you reason over that data.',
        variant: 'concept',
      },
      {
        title: 'Build a 3-step analysis workflow',
        content: '1. Create a new workflow and add 3 steps.\n2. Step 1 \u2014 Add an Extraction task. Select a SearchSet with fields relevant to your document.\n3. Step 2 \u2014 Add a Prompt task. Write a prompt that analyzes the extracted data.\n4. Step 3 \u2014 Add a Formatter task. Write a template that structures the final output.\n5. Select a document and run the workflow. Observe how data flows through each step.\n6. Review each step\'s output individually using the step-by-step output panel.',
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
    estimatedMinutes: 20,
  },
  {
    id: 'advanced_nodes',
    number: 6,
    title: 'Advanced Nodes',
    subtitle: 'Parallel Tasks & Power Nodes',
    description: 'Process a sample budget justification document using Code Execution to validate totals and parallel tasks for concurrent processing.',
    objectives: [
      'Add the sample budget justification to your workspace',
      'Use a Code Execution node to compute and verify budget totals',
      'Run 2+ tasks in parallel within a single step',
    ],
    tips: [
      'The budget has personnel costs, supplies, travel, and subaward line items that should sum to $542,800',
      'Use Code Execution to parse extracted numbers and compute sums for validation',
      'Add a parallel Prompt task alongside Code Execution to generate a budget narrative',
    ],
    lessons: [
      {
        title: 'Beyond extraction and prompts',
        content: 'Vandalizer has 17 different node types. So far you\'ve used Extraction, Prompt, and Format \u2014 but the advanced nodes let you go much further:\n\n\u2022 **Code Execution** \u2014 Run sandboxed Python to transform data, do calculations, or apply custom logic.\n\u2022 **API Call** \u2014 Make HTTP requests to external services.\n\u2022 **Research** \u2014 Two-pass analysis: first analyzes the data, then synthesizes findings.\n\u2022 **Crawler** \u2014 Fetch and extract text from websites.\n\u2022 **Add Document / Add Website** \u2014 Inject additional context mid-workflow.\n\u2022 **Browser Automation** \u2014 Drive a Chrome browser session for complex web interactions.',
        variant: 'concept',
      },
      {
        title: 'Key terms',
        content: 'Parallel Tasks \u2014 Multiple tasks within a single step run concurrently using a thread pool. Their results are collected and passed to the next step together.\n\nCode Execution \u2014 Runs Python in a restricted sandbox with a 10-second timeout. The previous step\'s output is available as `input_data`. Your code should assign its result to `output`.\n\nAPI Call \u2014 Supports GET, POST, PUT, and PATCH methods. You can include headers for authentication and use the previous step\'s output in the request body.\n\nResearch Node \u2014 Performs two-stage analysis: first passes through the data to identify patterns, then synthesizes findings into a coherent report.',
        variant: 'key-terms',
      },
      {
        title: 'Code Execution: custom logic in your pipeline',
        content: 'The Code Execution node lets you write Python that runs inside your workflow. This is powerful for:\n\n\u2022 **Data transformation** \u2014 Normalize dates, convert currencies, merge fields.\n\u2022 **Calculations** \u2014 Compute totals, percentages, or ratios from extracted numbers.\n\u2022 **Filtering** \u2014 Remove irrelevant results or flag outliers.\n\u2022 **Format conversion** \u2014 Reshape JSON into a different structure.\n\nThe code runs in a sandbox: no file system access, no network access, no imports beyond the standard library.',
        variant: 'concept',
      },
      {
        title: 'Running tasks in parallel',
        content: 'Within a single step, you can add multiple tasks. These tasks run concurrently \u2014 the workflow engine uses a thread pool to execute them simultaneously.\n\nThis is useful when you need multiple independent operations:\n\u2022 Extract from two different SearchSets at the same time\n\u2022 Call multiple APIs in parallel\n\u2022 Run an extraction while simultaneously fetching enrichment data from a website\n\nTo add parallel tasks, open a step in the workflow editor and click "Add Task" multiple times.',
        variant: 'concept',
      },
      {
        title: 'Build a workflow with advanced nodes',
        content: '1. Create a workflow with at least 3 steps.\n2. In one step, add a Code Execution task. Write Python that transforms the previous step\'s output.\n3. Or, add an API Call task that fetches data from an external source.\n4. In another step, add 2 tasks to run in parallel.\n5. Run the workflow and review how parallel tasks\' outputs are combined.',
        variant: 'walkthrough',
      },
    ],
    xp: 200,
    icon: 'Puzzle',
    estimatedMinutes: 25,
  },
  {
    id: 'output_delivery',
    number: 7,
    title: 'Output & Delivery',
    subtitle: 'Produce Real Deliverables',
    description: 'Process a sample Year-2 progress report and produce downloadable deliverables. Extract accomplishments, publications, and budget data, then export as a report or CSV.',
    objectives: [
      'Add the sample progress report to your workspace',
      'Create a workflow with an output node (Document Renderer, Data Export, etc.)',
      'Run the workflow and download the generated output file',
    ],
    tips: [
      'The progress report has publications, students trained, and budget expenditures to extract',
      'Document Renderer is great for producing a formatted summary report',
      'Data Export with CSV format works well for the budget expenditure data',
    ],
    lessons: [
      {
        title: 'From analysis to deliverables',
        content: 'So far, your workflows produce text output that you view in the app. But real research administration often requires deliverables: compliance reports to submit, data exports for spreadsheets, or document packages with multiple files.\n\nVandalizer\'s output nodes transform your workflow results into downloadable files:\n\n\u2022 **Document Renderer** \u2014 Generates a markdown or text file from your workflow output.\n\u2022 **Data Export** \u2014 Exports structured data as JSON or CSV.\n\u2022 **Package Builder** \u2014 Creates a ZIP archive containing multiple output files.\n\u2022 **Form Filler** \u2014 Takes a template with placeholders and fills it with extracted data.',
        variant: 'concept',
      },
      {
        title: 'Key terms',
        content: 'Document Renderer \u2014 Takes the previous step\'s text output and wraps it into a downloadable file.\n\nData Export \u2014 Converts structured JSON data into CSV or JSON format. When using CSV, each key becomes a column header.\n\nPackage Builder \u2014 Collects outputs from multiple steps and bundles them into a single ZIP file.\n\nForm Filler \u2014 Uses a template string with placeholder syntax to produce a filled-in version of your template.\n\nIs Output \u2014 A flag on steps that marks them as output steps. Only steps marked "is_output" contribute to the final downloadable result.',
        variant: 'key-terms',
      },
      {
        title: 'Designing end-to-end deliverable workflows',
        content: 'The most powerful workflows go from raw document to finished deliverable in one run:\n\n1. **Extract** \u2014 Pull structured data from the source document.\n2. **Analyze** \u2014 Use Prompt nodes to reason over the data, flag issues, or generate summaries.\n3. **Render** \u2014 Use output nodes to produce the final deliverable.\n\nThe result: upload a grant proposal, click Run, and download a completed compliance checklist.',
        variant: 'concept',
      },
      {
        title: 'Build a deliverable workflow',
        content: '1. Start with a workflow that extracts and analyzes data (from Module 3).\n2. Add a new step at the end of your workflow.\n3. Add a Document Renderer or Data Export task to that step.\n4. For Document Renderer: the previous step\'s output will be rendered as a downloadable file.\n5. For Data Export: choose JSON or CSV format.\n6. Run the workflow on a document.\n7. In the results panel, you\'ll see a download link for the generated file.',
        variant: 'walkthrough',
      },
    ],
    xp: 200,
    icon: 'FileOutput',
    estimatedMinutes: 20,
  },
  {
    id: 'validation_qa',
    number: 8,
    title: 'Validation & QA',
    subtitle: 'Ensure Quality at Scale',
    description: 'Add validation to your NSF proposal workflow from Module 1. Define quality checks that verify your extraction produces correct results, then run validation to measure accuracy.',
    objectives: [
      'Open your workflow from Module 1 (or create a new one for the NSF proposal)',
      'Create a validation plan with 2+ quality checks',
      'Run validation and review the results',
    ],
    tips: [
      'This module reuses the NSF proposal from Module 1 - no new documents needed',
      'Start with checks like "PI Name is not null" and "Total Budget is a valid number"',
      'Use auto-generated validation checks as a starting point, then customize',
    ],
    lessons: [
      {
        title: 'Why validation matters',
        content: 'An extraction workflow that works on one document might fail on the next. Different document layouts, writing styles, or terminology can cause the LLM to miss fields or return incorrect values.\n\nValidation lets you define what "correct" looks like for your workflow, test it against sample documents, and track reliability over time.',
        variant: 'concept',
      },
      {
        title: 'Key terms',
        content: 'Validation Plan \u2014 A list of quality checks that define what correct output looks like for your workflow.\n\nValidation Input \u2014 Sample documents or text used to test the workflow.\n\nValidation Run \u2014 An execution of the workflow against validation inputs, graded against the validation plan.\n\nQuality History \u2014 A log of validation run scores over time for detecting regressions.\n\nImprovement Suggestions \u2014 LLM-generated tips for improving extraction accuracy based on validation results.',
        variant: 'key-terms',
      },
      {
        title: 'Building effective validation plans',
        content: 'Good validation plans check multiple dimensions of quality:\n\n\u2022 **Completeness** \u2014 Did the workflow extract all expected fields?\n\u2022 **Accuracy** \u2014 Do extracted values match the known-correct values?\n\u2022 **Format** \u2014 Are dates in the right format? Are numbers parsed correctly?\n\u2022 **Consistency** \u2014 When run multiple times, does the workflow produce the same results?\n\nStart with 2-3 high-value checks and expand as you gain confidence.',
        variant: 'concept',
      },
      {
        title: 'Set up validation for your workflow',
        content: '1. Open your workflow in the editor and go to the Validate tab.\n2. Add validation inputs \u2014 paste sample text or select documents.\n3. Create a validation plan with at least 2 quality checks.\n4. Run validation. The system executes your workflow and grades the results.\n5. Review the results: which checks passed, which failed, and why.\n6. Use improvement suggestions to iterate on your extraction.\n7. Check quality history to see how your workflow improves over time.',
        variant: 'walkthrough',
      },
      {
        title: 'Validation as a safety net',
        content: 'The best time to set up validation is before you need it. When you change your SearchSet fields, update a prompt, or when the underlying LLM model is updated, your workflow\'s behavior might change. If you have a validation plan, you can re-run it immediately to check for regressions.',
        variant: 'insight',
      },
    ],
    xp: 250,
    icon: 'ShieldCheck',
    estimatedMinutes: 20,
  },
  {
    id: 'batch_processing',
    number: 9,
    title: 'Batch Processing',
    subtitle: 'Process at Scale',
    description: 'Process three sample NSF proposals in batch mode. Each proposal is from a different PI (Lopez, Kim, Okafor) with different research areas and budgets.',
    objectives: [
      'Add 3 sample batch proposals to your workspace',
      'Run a workflow in batch mode against all 3 documents',
      'Verify all 3 complete successfully with correct PI names',
    ],
    tips: [
      'Use your extraction workflow from Module 1 or 2, or create a new one',
      'The three proposals have PIs: Dr. Maria Lopez, Dr. Robert Kim, Dr. Amara Okafor',
      'Check that all 3 documents complete successfully before marking done',
    ],
    lessons: [
      {
        title: 'Single vs. batch execution',
        content: 'So far you\'ve been running workflows on one document at a time. Batch mode lets you process multiple documents in a single operation.\n\nIn batch mode, the workflow runs once per document, sequentially. Each document gets its own WorkflowResult, and you can monitor progress for the entire batch.\n\nThis is the core value proposition of Vandalizer: define a workflow once, validate it, then run it across hundreds of documents with confidence.',
        variant: 'concept',
      },
      {
        title: 'Key terms',
        content: 'Batch Mode \u2014 Runs the workflow once per selected document. Each execution is independent.\n\nBatch ID \u2014 A unique identifier for the batch. All results share this ID.\n\nSession ID \u2014 Each individual document execution within a batch has its own session ID.\n\nBatch Status \u2014 Aggregated view: how many completed, failed, or are still running.',
        variant: 'key-terms',
      },
      {
        title: 'Monitoring and debugging batch runs',
        content: 'When running a batch:\n\n\u2022 **Real-time progress** \u2014 The UI shows which document is currently processing.\n\u2022 **Per-document results** \u2014 Each document\'s result is stored independently.\n\u2022 **Error handling** \u2014 Common failures include documents that are too long, unexpected formats, or missing expected fields.\n\nAlways test your workflow on a single document before running a batch.',
        variant: 'concept',
      },
      {
        title: 'Choosing the right model for batch work',
        content: 'Model selection matters more for batch processing because costs and time multiply across documents. Consider speed, cost, accuracy, and data privacy tradeoffs.\n\nYou can override the model per-workflow or per-task. Consider using a faster model for format/prompt steps and a more capable model for extraction steps.',
        variant: 'insight',
      },
      {
        title: 'Run your first batch',
        content: '1. Ensure you have a workflow that works reliably on a single document.\n2. Upload at least 3 documents of the same type to your workspace.\n3. Select all 3 documents, then open your workflow.\n4. Choose "Batch" mode.\n5. Start the batch. Watch the real-time progress.\n6. When complete, review the results for each document.\n7. If any failed, inspect the error, fix the issue, and re-run just the failed documents.',
        variant: 'walkthrough',
      },
    ],
    xp: 250,
    icon: 'Play',
    estimatedMinutes: 25,
  },
  {
    id: 'governance',
    number: 10,
    title: 'Collaboration & Governance',
    subtitle: 'Share and Standardize',
    description: 'The final module before your Vandal Workflow Architect certification. Demonstrate that you can organize, verify, and share production-ready workflows across your team. Complete this and you earn your VWA credential.',
    objectives: [
      'Mark a workflow as verified in the workflow settings',
      'Use workflows across personal and team contexts',
      'No new documents needed - uses workflows you have already built',
    ],
    tips: [
      'Switch into a shared team if you want to practice collaboration flows',
      'Export workflows as .vandalizer.json files to share with teammates',
      'Verified workflows signal to your team that a workflow is production-ready',
    ],
    lessons: [
      {
        title: 'Organizing for reuse',
        content: 'As your team builds more workflows, organization becomes critical. Use personal work for drafting, then move the workflows your team should reuse into shared team libraries and verified collections.\n\nThink about organization in terms of ownership and audience:\n\u2022 **Personal work** \u2014 early drafts, experiments, and one-off variations.\n\u2022 **Team libraries** \u2014 shared workflows your group actively maintains.\n\u2022 **Verified collections** \u2014 approved workflows that set team standards.',
        variant: 'concept',
      },
      {
        title: 'Key terms',
        content: 'Personal work \u2014 Workflows and resources that only you can see and edit.\n\nVerified \u2014 A flag indicating the workflow has been tested, validated, and approved for production use.\n\nExport (.vandalizer.json) \u2014 A JSON file containing the complete workflow definition. Can be shared and imported.\n\nTeam \u2014 A group of users who share access to team workflows, libraries, and folders. Members have roles: owner, admin, or member.',
        variant: 'key-terms',
      },
      {
        title: 'The verification workflow',
        content: 'Marking a workflow as "verified" is a governance practice. It signals to your team that:\n\n1. The workflow has been tested on representative documents.\n2. A validation plan exists and passes consistently.\n3. The output format meets the team\'s requirements.\n4. The workflow is ready for production use.\n\nVerification isn\'t a technical gate \u2014 it\'s a team communication tool.',
        variant: 'concept',
      },
      {
        title: 'Sharing workflows across teams',
        content: 'Workflows can be shared in two ways:\n\n\u2022 **Within the same team** \u2014 Duplicate or adapt workflows inside the team workspace and library.\n\u2022 **Cross-team sharing via export/import** \u2014 Export a workflow as a .vandalizer.json file. Send it to a colleague, who can import it.\n\nSharing verified workflows establishes organizational standards.',
        variant: 'concept',
      },
      {
        title: 'Establish your workflow governance',
        content: '1. Pick a workflow that is ready to share beyond your personal work.\n2. Build or duplicate that workflow into the team context where others should reuse it.\n3. Make sure your workflow has a clear description.\n4. If you completed Module 8, ensure your validation plan passes.\n5. Mark the workflow as verified in the workflow settings.\n6. Try exporting and importing the workflow.\n7. You now have a verified, portable, well-documented workflow.',
        variant: 'walkthrough',
      },
      {
        title: 'Building a culture of reuse',
        content: 'The highest-performing teams maintain a library of verified workflows that cover common document types, then adapt and extend them as needed.\n\nBy completing this module, you\'ve demonstrated every skill in the Vandal Workflow Architect program: understanding AI, decomposing processes, designing pipelines, building extractions, chaining multi-step workflows, using advanced nodes, producing deliverables, validating quality, processing at scale, and governing shared workflows.\n\nYou\'re now a certified VWA \u2014 the person on your team who knows how to turn any document-heavy process into a reliable, AI-powered pipeline. That\'s a rare and valuable skill.',
        variant: 'insight',
      },
    ],
    xp: 300,
    icon: 'FolderGit2',
    estimatedMinutes: 15,
  },
]

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
          {result.passed && (
            <div className="flex gap-0.5">
              {Array.from({ length: 3 }).map((_, i) => (
                <Star
                  key={i}
                  size={14}
                  className={cn(
                    'transition-all duration-300',
                    i < result.stars ? 'text-yellow-400 fill-yellow-400' : 'text-gray-300',
                  )}
                />
              ))}
            </div>
          )}
        </div>
        <button onClick={onDismiss} className="text-gray-400 hover:text-gray-600">
          <X size={16} />
        </button>
      </div>
      <div className="space-y-1.5">
        {result.checks.map((check: ValidationCheck, i: number) => (
          <div key={i} className="flex items-center gap-2 text-sm">
            {check.passed
              ? <span className="text-green-600 shrink-0">&#10003;</span>
              : <X size={14} className="text-red-500 shrink-0" />
            }
            <span className={check.passed ? 'text-green-800' : 'text-red-700'}>{check.name}</span>
            <span className="text-gray-500 text-xs">&mdash; {check.detail}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Certification() {
  const { progress, loading, validate, complete, provision, getExercise, submitAssessment } = useCertification()
  const { toast } = useToast()
  const [activeModule, setActiveModule] = useState<string | null>(null)
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null)
  const [completionResult, setCompletionResult] = useState<CompletionResult | null>(null)
  const [validating, setValidating] = useState(false)
  const [completing, setCompleting] = useState(false)
  const [provisioning, setProvisioning] = useState(false)
  const [submittingAssessment, setSubmittingAssessment] = useState(false)
  const [exercise, setExercise] = useState<CertExercise | null>(null)
  const detailRef = useRef<HTMLDivElement>(null)

  const level = progress?.level || 'novice'
  const levelConfig = LEVEL_CONFIG[level] || LEVEL_CONFIG.novice
  const totalXp = progress?.total_xp || 0

  // XP count-up animation
  const [displayXp, setDisplayXp] = useState(totalXp)
  useEffect(() => {
    if (displayXp === totalXp) return
    const diff = totalXp - displayXp
    const steps = Math.min(Math.abs(diff), 20)
    const increment = diff / steps
    let step = 0
    const timer = setInterval(() => {
      step++
      if (step >= steps) {
        setDisplayXp(totalXp)
        clearInterval(timer)
      } else {
        setDisplayXp(prev => Math.round(prev + increment))
      }
    }, 50)
    return () => clearInterval(timer)
  }, [totalXp]) // eslint-disable-line react-hooks/exhaustive-deps
  const completedCount = useMemo(() => {
    if (!progress) return 0
    return Object.values(progress.modules).filter(m => m.completed).length
  }, [progress])

  // Find next level threshold
  const currentLevelIdx = LEVEL_THRESHOLDS.findIndex(l => l.name === level)
  const nextLevel = LEVEL_THRESHOLDS[currentLevelIdx + 1] || LEVEL_THRESHOLDS[LEVEL_THRESHOLDS.length - 1]
  const prevLevel = LEVEL_THRESHOLDS[currentLevelIdx] || LEVEL_THRESHOLDS[0]

  const overallPct = (totalXp / TOTAL_XP) * 100

  const isModuleLocked = useCallback((moduleId: string): boolean => {
    const module = MODULES.find(m => m.id === moduleId)
    if (!module) return true
    if (module.number === 0) return false // Module 0 always unlocked
    const prevModule = MODULES.find(m => m.number === module.number - 1)
    if (!prevModule) return false
    return !progress?.modules[prevModule.id]?.completed
  }, [progress])

  // Load exercise when active module changes
  useEffect(() => {
    if (!activeModule) {
      setExercise(null)
      return
    }
    getExercise(activeModule).then(setExercise).catch(() => setExercise(null))
  }, [activeModule, getExercise])

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
      // Check if a tier was just completed
      checkTierCompletion(moduleId)
    } catch {
      // Validation failed - show what's missing
      toast('Module not ready — check the requirements below', 'error')
      await handleValidate(moduleId)
    } finally {
      setCompleting(false)
    }
  }

  const handleProvision = async (moduleId: string) => {
    setProvisioning(true)
    try {
      await provision(moduleId)
    } finally {
      setProvisioning(false)
    }
  }

  const handleSubmitAssessment = async (moduleId: string, answers: Record<string, string>) => {
    setSubmittingAssessment(true)
    try {
      await submitAssessment(moduleId, answers)
    } finally {
      setSubmittingAssessment(false)
    }
  }

  const handleModuleClick = (moduleId: string) => {
    if (isModuleLocked(moduleId)) return
    setActiveModule(activeModule === moduleId ? null : moduleId)
    setValidationResult(null)
    // Scroll to detail after render
    setTimeout(() => detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 100)
  }

  // Check if completing this module finishes a tier
  const [tierCelebration, setTierCelebration] = useState<{ tierName: string; message: string } | null>(null)

  const checkTierCompletion = useCallback((justCompletedModuleId: string) => {
    for (const tier of TIERS) {
      if (!tier.moduleIds.includes(justCompletedModuleId)) continue
      const allComplete = tier.moduleIds.every(id => {
        if (id === justCompletedModuleId) return true // Just completed
        return progress?.modules[id]?.completed
      })
      if (allComplete) {
        setTierCelebration({ tierName: tier.name, message: tier.celebration })
      }
    }
  }, [progress])

  // Auto-navigate to next module after celebration dismissal
  const handleCelebrationDismiss = useCallback(() => {
    const completedModuleId = completionResult?.module_id
    setCompletionResult(null)
    setTierCelebration(null)

    if (completedModuleId) {
      const completedModule = MODULES.find(m => m.id === completedModuleId)
      if (completedModule) {
        const nextModule = MODULES.find(m => m.number === completedModule.number + 1)
        if (nextModule && !isModuleLocked(nextModule.id)) {
          // Auto-navigate to next module
          setActiveModule(nextModule.id)
          toast(`Next up: ${nextModule.title}`, 'info')
          setTimeout(() => detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 100)
          return
        }
      }
    }
    // Clear lesson localStorage for completed module
    if (completedModuleId) {
      localStorage.removeItem(`cert-lesson-${completedModuleId}`)
    }
  }, [completionResult, isModuleLocked, toast])

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
              <p className="text-sm text-gray-500 mb-2">
                Complete all 11 modules to earn your official certification
              </p>
              <div
                className="flex items-center gap-2 px-3 py-2 mb-4 border border-yellow-200 bg-yellow-50/60"
                style={{ borderRadius: 'var(--ui-radius, 12px)' }}
              >
                <Award size={16} className="text-yellow-600 shrink-0" />
                <p className="text-xs text-yellow-800">
                  <span className="font-bold">Vandal Workflow Architect (VWA)</span> — a University of Idaho credential recognizing your ability to design, build, and deploy AI-powered document workflows for research administration.
                </p>
              </div>

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
                  <span className="text-gray-500">/ 11 modules</span>
                </div>
                <div
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-50 border border-gray-200 text-sm"
                  style={{ borderRadius: 'var(--ui-radius, 12px)' }}
                >
                  <Zap size={14} className="text-highlight" style={{ color: 'var(--highlight-color)' }} />
                  <span className="font-semibold text-gray-900">{displayXp}</span>
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

        {/* Journey Map (replaces flat module grid) */}
        <div>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Training Modules</h2>
          <JourneyMap
            modules={MODULES}
            progress={progress}
            activeModule={activeModule}
            isModuleLocked={isModuleLocked}
            onModuleClick={handleModuleClick}
          />
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
                provisioned_docs: progress.modules[activeModuleDef.id].provisioned_docs,
                lab_space_id: progress.modules[activeModuleDef.id].lab_space_id,
                self_assessment: progress.modules[activeModuleDef.id].self_assessment,
              } : null}
              onValidate={() => handleValidate(activeModuleDef.id)}
              onComplete={() => handleComplete(activeModuleDef.id)}
              onProvision={() => handleProvision(activeModuleDef.id)}
              onSubmitAssessment={(answers) => handleSubmitAssessment(activeModuleDef.id, answers)}
              exercise={exercise}
              validating={validating}
              completing={completing}
              provisioning={provisioning}
              submittingAssessment={submittingAssessment}
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
        <CelebrationOverlay
          result={completionResult}
          onDismiss={handleCelebrationDismiss}
          tierCelebration={tierCelebration}
        />
      )}
    </PageLayout>
  )
}
