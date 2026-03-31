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
import { useAuth } from '../hooks/useAuth'
import { useToast } from '../contexts/ToastContext'
import { cn } from '../lib/cn'
import type { ModuleDefinition, ValidationResult, CompletionResult, ValidationCheck, CertExercise } from '../types/certification'

// Components
import { CertifiedBanner } from '../components/certification/CertifiedBanner'
import { CelebrationOverlay } from '../components/certification/CelebrationOverlay'
import { ModuleDetail } from '../components/certification/ModuleDetail'
import { useQueryClient } from '@tanstack/react-query'
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
        objective: 'After this lesson, you\'ll be able to explain why LLMs make mistakes and why they\'re still useful.',
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
        title: 'What AI is genuinely good at',
        objective: 'After this lesson, you\'ll know which research admin tasks are best suited for AI automation.',
        content: 'AI excels at tasks that involve pattern recognition across large volumes of text:\n\n\u2022 **Extracting specific information** from long documents \u2014 Finding the PI name, budget, and project period in a 50-page proposal.\n\u2022 **Summarizing** \u2014 Condensing a progress report into key findings and milestones.\n\u2022 **Comparing across documents** \u2014 Identifying differences between two versions of a budget justification.\n\u2022 **Drafting routine text** \u2014 Generating first drafts of compliance summaries or progress report templates.\n\u2022 **Processing many documents consistently** \u2014 Applying the same extraction to 200 proposals and getting results in the same format every time.\n\nThe common thread: these are tasks where a human would be doing repetitive reading and data entry. AI handles the volume; you handle the judgment.',
        variant: 'concept',
      },
      {
        title: 'What AI is genuinely bad at',
        objective: 'After this lesson, you\'ll be able to identify AI limitations and avoid common pitfalls in research administration.',
        content: 'Honesty about AI\'s limitations is essential for responsible use in research administration:\n\n\u2022 **Judgment calls requiring institutional knowledge** \u2014 AI doesn\'t know your university\'s internal policies, political dynamics, risk tolerance, or historical context.\n\u2022 **Catching its own mistakes** \u2014 An LLM cannot reliably self-check. If it extracts the wrong budget figure, it won\'t flag the error. That\'s your job.\n\u2022 **Math** \u2014 LLMs frequently make arithmetic errors. Never trust an LLM to add up budget line items. Use code execution nodes for calculations.\n\u2022 **Novel or unusual document formats** \u2014 If a document doesn\'t follow standard patterns (hand-written notes, unusual layouts, scanned images with poor OCR), extraction quality drops significantly.\n\u2022 **Replacing professional judgment on compliance** \u2014 AI can flag potential issues, but determining whether a proposal actually meets regulatory requirements requires your expertise.\n\nThe pattern: AI is a powerful first-pass tool. It does the reading; you do the thinking.',
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
        objective: 'After this lesson, you\'ll be able to describe where AI fits in common research admin workflows and where it doesn\'t.',
        content: 'Here\'s what AI-assisted research administration looks like in practice:\n\n\u2022 **Proposal intake** \u2014 Upload 30 new proposals to a secure, institutionally managed AI environment. A workflow extracts PI name, agency, budget, and key dates from each one in minutes instead of hours \u2014 without exposing sensitive proposal data to consumer AI tools or free-tier services.\n\u2022 **Progress report processing** \u2014 Extract accomplishments, publications, and expenditures from annual reports. Flag any that are missing required sections.\n\u2022 **Compliance pre-screening** \u2014 Check proposals against a list of required elements (human subjects approval, data management plan, budget justification) and flag gaps.\n\u2022 **Subaward review** \u2014 Extract parties, amounts, and terms from subaward agreements. Compare against institutional templates.\n\nThe pattern in every case: AI does the first pass of extraction, you do the second pass of verification and judgment. The AI handles volume and consistency. You bring expertise and accountability.',
        variant: 'concept',
        diagram: 'ai-human-pattern',
      },
      {
        title: 'From chatbot to structured pipeline',
        objective: 'After this lesson, you\'ll understand the gap between consumer AI tools and a professional workflow system, and why that gap matters.',
        content: 'You may have used ChatGPT or Copilot to ask questions about a document. That works for one-off questions, but it fails for professional research administration work:\n\n\u2022 **Inconsistent format** \u2014 Ask the same question twice and you\'ll get differently structured answers.\n\u2022 **No audit trail** \u2014 There\'s no record of what was extracted, when, or from which document.\n\u2022 **Can\'t scale** \u2014 You can\'t (and in many cases shouldn\'t) paste 200 proposals into a chatbot one at a time.\n\u2022 **No verification** \u2014 There\'s no systematic way to check if the answers are correct.\n\nWorkflows solve all of these problems. A workflow defines exactly what to extract, produces consistent structured output, maintains a complete audit trail, runs across hundreds of documents, and can be validated for accuracy.\n\nThis is the bridge from "AI as a toy" to "AI as a professional tool." Over the next 10 modules, you\'ll learn to decompose your real processes, build workflows that handle them, validate those workflows for accuracy, and deploy them at scale. When you complete all 11 modules, you\'ll earn your Vandal Workflow Architect certification \u2014 a credential that says you can turn any document-heavy process into a reliable, AI-powered pipeline.',
        variant: 'insight',
      },
      {
        title: 'Glossary & Review',
        content: 'LLM (Large Language Model) \u2014 You\'ve now seen how LLMs are used to extract structured fields from grant proposals and summarize documents. The key: an LLM is a pattern-completion engine, not a thinking machine. It predicts likely text based on training patterns. When you build a workflow step, you\'re giving it patterns to match \u2014 the clearer your field names and prompts, the better the results.\n\nPrompt \u2014 The instructions you give an LLM. You\'ll write many of these as you build workflows. Quality matters: "Extract the PI name from the proposal cover page" outperforms "find the PI."\n\nHallucination \u2014 When an LLM generates a plausible-sounding value that isn\'t actually in the document. The #1 risk in research administration AI use. It\'s why you\'ll learn to build validation plans in Module 8.\n\nStructured Output \u2014 The mechanism that makes batch processing possible. Instead of free-form text, the LLM is constrained to return JSON matching your field definitions \u2014 same fields, same format, every document, every time.\n\nToken \u2014 The unit LLMs work in. Roughly \u00be of a word. Relevant when documents are very long \u2014 models have context limits that affect how much text they can process at once.\n\nRAG (Retrieval-Augmented Generation) \u2014 How the chat feature works. Relevant document excerpts are retrieved and provided to the LLM before it answers. This grounds responses in your actual documents rather than the LLM\'s training data.',
        variant: 'key-terms',
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
      'Use clear, descriptive field names in your Extraction that match the document labels',
      'After running, check that PI Name = Sarah Chen and Total Budget = $485,000',
    ],
    lessons: [
      {
        title: 'What is a workflow?',
        objective: 'After this lesson, you\'ll understand how workflows differ from ad-hoc chat and why that matters for research administration.',
        content: 'A workflow is a reusable pipeline that processes a document through a series of defined steps \u2014 build it once, run it against any document. Unlike ad-hoc chat, workflows produce consistent, structured output. That consistency is what lets you process 500 grant proposals the same way you process one.',
        variant: 'concept',
      },
      {
        title: 'What you\'ll build',
        content: 'Here\'s the end state for this module\'s lab exercise:\n\n\u2022 A workflow called something like "Grant Proposal Extractor"\n\u2022 An Extraction with at least 5 fields: PI Name, Total Budget, Sponsoring Agency, Project Period, Institution\n\u2022 A run result showing Dr. Sarah Chen extracted from the sample NSF proposal, with a budget of $485,000\n\nThe lessons that follow explain each piece. By the time you reach the lab, every step will be familiar.',
        variant: 'walkthrough',
      },
      {
        title: 'The document pipeline',
        objective: 'After this lesson, you\'ll understand what happens to a document between upload and extraction.',
        content: 'When you upload a document, Vandalizer processes it through several stages:\n\n1. **Text extraction** \u2014 The raw text is pulled from PDFs, DOCX, XLSX, and HTML files using specialized readers.\n2. **Chunking** \u2014 The text is split into overlapping segments for semantic search.\n3. **Embedding** \u2014 Each chunk is embedded into ChromaDB, a vector database, so it can be searched semantically.\n\nWhen a workflow runs an Extraction step, the LLM receives the full document text and your Extraction fields, and returns structured JSON with the extracted values.',
        variant: 'concept',
      },
      {
        title: 'Build your first workflow',
        objective: 'After this lesson, you\'ll be ready to run your first extraction workflow on a real document.',
        content: 'When you start the lab exercise, here\'s what you\'ll do:\n\n1. Click **Set Up Lab** below to load the sample NSF proposal into your workspace.\n2. Go to the **Library** tab and click **New** to create a new workflow.\n3. Give your workflow a clear name, like "Grant Proposal Extractor", and add a description such as "Extracts key details from grant proposals".\n4. Add a step and give it a name, like "Extract Grant Details". Then add an Extraction task to that step.\n5. In the Extraction task settings, select an existing Extraction or create a new one.\n6. Add at least 3 fields to your Extraction \u2014 for example: "Principal Investigator", "Funding Amount", "Sponsoring Agency".\n7. Select the sample NSF proposal, then click Run to execute the workflow.\n8. Review the extracted results in the output panel.',
        variant: 'walkthrough',
      },
      {
        title: 'Why structured extraction matters',
        content: 'Unstructured AI responses vary every time \u2014 different formatting, different phrasing, different levels of detail. Structured extraction forces the AI to return consistent, machine-readable JSON. This means you can reliably extract the same fields from hundreds of documents and compare, aggregate, or export the results. It turns documents from unstructured text into queryable data.',
        variant: 'insight',
      },
      {
        title: 'Glossary & Review',
        content: 'Workflow \u2014 You just built one. A saved pipeline that processes documents through a series of steps. The recipe analogy holds: define it once, run it against any document. The extraction workflow from this module is the foundation for everything that follows.\n\nStep \u2014 One stage in your pipeline. Your first workflow had one step (extraction). Later modules add reasoning and delivery steps to create more powerful pipelines.\n\nTask \u2014 The specific operation inside a step. The Extraction task you configured defined which fields the LLM should find and return as structured JSON.\n\nExtraction \u2014 The collection of fields you defined. Think of it as your data dictionary \u2014 it tells the LLM exactly what to look for and what format to return it in.\n\nExtract Key \u2014 Each individual field in your Extraction: "PI Name", "Total Budget", "Sponsoring Agency". Well-named extract keys get better results because the LLM uses the name as a clue about what to find.',
        variant: 'key-terms',
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
        title: 'From one workflow to many',
        objective: 'After this lesson, you\'ll be able to identify repeatable processes in your daily work that are ready for automation.',
        content: 'You\'ve built a basic workflow. Now the question is: what else in your office should be a workflow?\n\nModule 1 taught you the mechanics. This module gives you a framework for finding the processes worth automating. The pattern you\'re looking for: any task where you spend 80% of your time reading documents and 20% making decisions about what you found. The reading is automatable. The deciding stays yours.\n\nBy the end of this module, you\'ll have mapped a real process from your own work to a workflow architecture \u2014 not a hypothetical, but something you could actually build next.',
        variant: 'concept',
      },
      {
        title: 'Finding the repetition',
        objective: 'After this lesson, you\'ll have a practical test for identifying which processes to automate.',
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
        objective: 'After this lesson, you\'ll have a decision framework for choosing between Extraction, Code Execution, and keeping a step human.',
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
      {
        title: 'Glossary & Review',
        content: 'Use these five elements to describe any process you\'re considering automating. You\'ve seen them applied to proposal intake \u2014 now practice applying them to a process from your own work.\n\nInput \u2014 What triggers this process? Usually a document arriving: a proposal, a report, a subaward agreement, a budget justification.\n\nSteps \u2014 The discrete actions you take, in order. Each step has a clear purpose: "find the PI name," "check the budget," "write a summary."\n\nDecision Points \u2014 Where you apply judgment: "Is this budget reasonable?" "Does this meet compliance requirements?" These are where human expertise is essential and AI steps back.\n\nHandoffs \u2014 Where work passes between people: "Send to compliance officer for review," "Return to PI for corrections."\n\nOutput \u2014 What\'s produced at the end: a completed form, a summary report, a recommendation, data entered into a system.',
        variant: 'key-terms',
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
        objective: 'After this lesson, you\'ll be able to map each step in a process to a specific Vandalizer task type.',
        content: 'In Module 2, you decomposed a process into steps and identified which are AI-suitable vs. which stay human. Now you\'ll map each AI-suitable step to a specific Vandalizer task type \u2014 turning your process map into a buildable architecture.\n\nThe mapping is straightforward:\n\u2022 "Find information in a document" \u2192 Extraction task with an Extraction\n\u2022 "Analyze or summarize the extracted data" \u2192 Prompt task\n\u2022 "Compute, total, or apply rules" \u2192 Code Execution task\n\u2022 "Check a document for specific sections or elements" \u2192 Prompt task\n\u2022 "Produce a formatted report or export" \u2192 Document Renderer or Data Export\n\u2022 "Compare this document to another" \u2192 Add Document + Prompt task\n\nThe key insight: you\'re not starting from scratch asking "what can this tool do?" You\'re starting from your process and asking "which tool handles this step?"',
        variant: 'concept',
      },
      {
        title: 'The extract-reason-deliver pattern',
        objective: 'After this lesson, you\'ll understand the most reliable workflow pattern for research administration and why it works.',
        content: 'The most common and most effective workflow pattern in research administration has three phases:\n\n1. **Extract** \u2014 Pull structured data from the document. This is your Extraction step with a well-designed Extraction. The output is clean, consistent JSON.\n\n2. **Reason** \u2014 Analyze the extracted data. This might be a Prompt step that summarizes findings, a Code Execution step that computes totals, or both. The output is analysis or computed results.\n\n3. **Deliver** \u2014 Produce something useful. A formatted report, a CSV export, a compliance checklist, or structured data ready for your tracking system.\n\nThis pattern works because it separates concerns. If your final report is wrong, you can check: did the extraction get the right data? (Check step 1\'s output.) Did the analysis interpret it correctly? (Check step 2.) You can fix the broken step without rebuilding the whole workflow.',
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
        objective: 'After this lesson, you\'ll be able to design workflow output that makes human review fast rather than cumbersome.',
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
      {
        title: 'Glossary & Review',
        content: 'These are the design decisions you\'ll face for every workflow you build. You\'ve seen them applied in the compliance review walkthrough \u2014 use this as a reference when designing your own pipelines.\n\nStep granularity \u2014 How many steps should your workflow have? Each step should do one clear thing. If you can\'t describe a step\'s purpose in one sentence, split it.\n\nTask type selection \u2014 Choose the simplest task type that gets the job done. If you need structured data from a document, use Extraction \u2014 don\'t write a Prompt asking the LLM to produce JSON.\n\nData flow \u2014 Each step receives the previous step\'s output. Design your steps so the output of one naturally feeds the next. Extraction produces JSON; a Prompt can analyze that JSON; a Renderer can format the analysis.\n\nHuman checkpoints \u2014 Decide where a human should review before the workflow continues. In most research admin workflows, the answer is: review after the final output, not after every step.\n\nError tolerance \u2014 What happens if the LLM extracts a field incorrectly? Design your workflow so errors are visible in the output, not hidden. Show source data alongside conclusions.',
        variant: 'key-terms',
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
      'Create an Extraction with 15+ fields covering all document sections',
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
        objective: 'After this lesson, you\'ll know when to use two-pass vs. consensus extraction and what quality tradeoff you\'re making.',
        diagram: 'extraction-output-example',
        content: 'Vandalizer offers two extraction strategies:\n\n**One-pass extraction** sends the document and field definitions to the LLM in a single call. It\'s faster and cheaper, but can miss nuances in complex documents.\n\n**Two-pass extraction** (the default) works in two stages:\n\u2022 Pass 1: The LLM creates a draft extraction, thinking through each field.\n\u2022 Pass 2: A second LLM call refines the draft, using structured output to produce clean, validated JSON.\n\nThe two-pass approach is more accurate because the second pass can correct mistakes from the first, and the structured output format prevents formatting errors.',
        variant: 'concept',
        knowledgeCheck: {
          question: 'What makes two-pass extraction more accurate than one-pass?',
          options: [
            { text: 'It processes large documents by splitting them into chunks', correct: false, explanation: 'That\'s chunking, a separate feature. Two-pass is about using a second LLM call to refine the first draft.' },
            { text: 'A second LLM call refines the first draft, correcting mistakes and enforcing structured output', correct: true, explanation: 'Correct! The second pass reviews and cleans up the first pass, producing validated JSON with fewer errors.' },
            { text: 'It uses a smarter model for the second pass to catch errors from the first', correct: false, explanation: 'Both passes use the same model. The improvement comes from the second pass having a draft to refine, not from a model change.' },
            { text: 'It runs the same extraction twice and averages the results', correct: false, explanation: 'That\'s consensus repetition, not two-pass. Two-pass uses the first draft as context for a more accurate second attempt.' },
          ],
        },
      },
      {
        title: 'Configuring fields for accuracy',
        objective: 'After this lesson, you\'ll be able to configure extraction fields that minimize hallucinations and missed values.',
        content: 'The way you configure your Extraction fields directly impacts extraction quality:\n\n**Field names** should be specific and unambiguous. "PI Name" is better than "Name". "Total Budget (USD)" is better than "Budget".\n\n**Enum values** constrain a field to a set of allowed options. For a field like "Document Type", you might set enum values to ["Grant Proposal", "Progress Report", "Budget Justification"]. This prevents the LLM from inventing categories.\n\n**Optional fields** should be marked as such. If a field like "Co-PI" won\'t appear in every document, marking it optional tells the extraction engine not to hallucinate a value when one doesn\'t exist.\n\n**Field descriptions** (in the title/searchphrase) give the LLM additional context about what to look for.',
        variant: 'concept',
        knowledgeCheck: {
          question: 'When should you mark an Extraction field as optional?',
          options: [
            { text: 'When you\'re not sure what value to expect', correct: false, explanation: 'Uncertainty about value isn\'t the reason to mark optional. Optional means the field might not exist in the document at all.' },
            { text: 'When the field may not appear in every document of that type', correct: true, explanation: 'Correct! Marking a field optional tells the extraction engine not to hallucinate a value when the field simply isn\'t present.' },
            { text: 'When you want the LLM to skip the field to save processing time', correct: false, explanation: 'Optional fields still get processed — the flag tells the engine it\'s acceptable to return null, not to skip the field.' },
            { text: 'When the field contains numbers instead of text', correct: false, explanation: 'Data type doesn\'t determine optionality. A budget figure might always be present — that\'s not optional.' },
          ],
        },
      },
      {
        title: 'Build a comprehensive extraction',
        content: '1. Create a new Extraction or expand an existing one to 15+ fields.\n2. Group related fields logically \u2014 e.g., personnel fields together, budget fields together.\n3. Use enum_values for any categorical field (status, type, category).\n4. Mark fields that may not always be present as optional.\n5. Add descriptive titles to help the LLM understand ambiguous fields.\n6. Run the extraction on a test document and review the results.\n7. Iterate: adjust field names and add enum constraints for any fields that extracted poorly.',
        variant: 'walkthrough',
      },
      {
        title: 'When to use consensus repetition',
        content: 'Consensus repetition runs the same extraction 3 times and takes the majority answer for each field. Use it when the stakes are high \u2014 compliance data, financial figures, legal terms \u2014 and the cost of an incorrect extraction outweighs the 3x processing cost. For routine extractions or exploratory work, two-pass is usually sufficient.',
        variant: 'insight',
      },
      {
        title: 'Glossary & Review',
        content: 'Structured Output \u2014 You\'ve now seen this in action: the LLM is constrained to return data matching a schema built from your Extraction fields. This is what prevents formatting errors and ensures you get the same JSON structure every time, regardless of how different the source documents look.\n\nThinking Mode \u2014 When enabled, the LLM reasons step-by-step before answering. Two-pass extraction uses Thinking Mode in Pass 1 for accuracy and disables it in Pass 2 for speed \u2014 you get both benefits.\n\nConsensus Repetition \u2014 Runs the same extraction 3 times and takes the majority answer for each field. The right choice when stakes are high: compliance data, financial figures, legal terms. 3x the cost, but highest accuracy.\n\nChunking \u2014 When you have many fields (20+), the extraction splits into smaller batches to stay within the LLM\'s context window. Vandalizer handles this automatically when you exceed the threshold.',
        variant: 'key-terms',
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
        objective: 'After this lesson, you\'ll understand how data flows between steps in a multi-step workflow.',
        diagram: 'workflow-result-example',
        content: 'A multi-step workflow forms a pipeline where each step\'s output becomes the next step\'s input. The workflow engine executes steps in order (technically, in topological order of a directed acyclic graph, or DAG).\n\nFor example, a 3-step workflow might work like this:\n\u2022 Step 1 (Extraction): Pulls structured fields from the document \u2192 outputs JSON.\n\u2022 Step 2 (Prompt): Receives that JSON and asks the LLM to analyze it \u2192 outputs analysis text.\n\u2022 Step 3 (Format): Takes the analysis and formats it into a clean report \u2192 outputs final document.\n\nEach step can see the output of the step before it, creating a chain of increasingly refined output.',
        variant: 'concept',
        knowledgeCheck: {
          question: 'What does a step receive as input by default?',
          options: [
            { text: 'The original uploaded document, regardless of step position', correct: false, explanation: 'After step 1, the input source switches to the previous step\'s output, not the original document.' },
            { text: 'The output of the previous step', correct: true, explanation: 'Correct! Each step\'s default input source is "step_input" — the output of the step before it in the chain.' },
            { text: 'All outputs from every previous step, combined into one', correct: false, explanation: 'Steps receive their immediate predecessor\'s output by default, not a combined history of all prior steps.' },
            { text: 'A fresh, empty context with only the system prompt', correct: false, explanation: 'Steps are connected \u2014 each one builds on the previous step\'s work.' },
          ],
        },
      },
      {
        title: 'The Prompt node: reasoning over data',
        objective: 'After this lesson, you\'ll know when to use an Extraction task vs. a Prompt task and why the distinction matters.',
        content: 'The Prompt node is one of the most powerful tools in your workflow. It sends the previous step\'s output to the LLM along with your custom prompt, and returns the LLM\'s response.\n\nUse it to:\n\u2022 Summarize extracted data\n\u2022 Compare and analyze\n\u2022 Generate recommendations\n\u2022 Transform formats\n\nThe key insight is that extraction gives you structured data, and prompts let you reason over that data.',
        variant: 'concept',
        knowledgeCheck: {
          question: 'What\'s the key difference between an Extraction task and a Prompt task?',
          options: [
            { text: 'Extraction is faster; Prompt produces more detailed output', correct: false, explanation: 'Speed isn\'t the defining difference. The distinction is about what kind of operation you\'re performing.' },
            { text: 'Extraction pulls structured fields from a document; Prompt reasons over data with a custom instruction', correct: true, explanation: 'Correct! Use Extraction to get structured data out of a document. Use Prompt to analyze, summarize, or reason over that data.' },
            { text: 'Extraction only works on PDFs; Prompt works on any text format', correct: false, explanation: 'Both task types work on text \u2014 the difference is in the operation, not the document format.' },
            { text: 'Extraction supports Thinking Mode; Prompt does not', correct: false, explanation: 'Both task types can use Thinking Mode. The distinction is about extraction vs. reasoning, not about model settings.' },
          ],
        },
      },
      {
        title: 'Build a 3-step analysis workflow',
        content: '1. Create a new workflow and add 3 steps.\n2. Step 1 \u2014 Add an Extraction task. Select an Extraction with fields relevant to your document.\n3. Step 2 \u2014 Add a Prompt task. Write a prompt that analyzes the extracted data.\n4. Step 3 \u2014 Add a Formatter task. Write a template that structures the final output.\n5. Select a document and run the workflow. Observe how data flows through each step.\n6. Review each step\'s output individually using the step-by-step output panel.',
        variant: 'walkthrough',
      },
      {
        title: 'Design principle: extract first, reason second',
        content: '*You\'ve seen this principle before in Module 3 \u2014 that\'s intentional. Spaced repetition builds retention. Let\'s revisit it and see how it applies when chaining multiple steps.*\n\nA common mistake is trying to do everything in one big prompt. Instead, separate extraction (getting facts from documents) from reasoning (drawing conclusions from those facts). This makes each step simpler, more reliable, and easier to debug. If your final output is wrong, you can check: did the extraction step get the right data? Or did the prompt step misinterpret it? This separation is what makes workflows more reliable than one-shot prompting.',
        variant: 'insight',
      },
      {
        title: 'Glossary & Review',
        content: 'Input Source \u2014 Controls what data a step receives. You\'ve now seen "step_input" in action \u2014 the default that passes each step\'s output to the next. Other options let you inject a specific document or all workflow documents at any point in the chain.\n\nPrompt Node \u2014 The reasoning engine in your pipeline. It takes the previous step\'s output and your custom instruction, and returns the LLM\'s analysis. You used it to transform extracted JSON into a compliance summary.\n\nFormat Node \u2014 Transforms structured data into formatted text (markdown, plain text). Use it when you want a human-readable report from raw extracted data without writing a custom prompt.\n\nPost-process Prompt \u2014 An optional final LLM call on any node\'s output. Use it to clean up or lightly reformat results without adding a full extra step to your pipeline.',
        variant: 'key-terms',
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
        title: 'Code Execution: custom logic in your pipeline',
        objective: 'After this lesson, you\'ll know which kinds of logic belong in Code Execution rather than Prompt nodes.',
        content: 'The Code Execution node lets you write Python that runs inside your workflow. This is powerful for:\n\n\u2022 **Data transformation** \u2014 Normalize dates, convert currencies, merge fields.\n\u2022 **Calculations** \u2014 Compute totals, percentages, or ratios from extracted numbers.\n\u2022 **Filtering** \u2014 Remove irrelevant results or flag outliers.\n\u2022 **Format conversion** \u2014 Reshape JSON into a different structure.\n\nThe code runs in a sandbox: no file system access, no network access, no imports beyond the standard library.',
        variant: 'concept',
        knowledgeCheck: {
          question: 'Which task should use Code Execution instead of a Prompt node?',
          options: [
            { text: 'Extracting structured fields from a grant proposal', correct: false, explanation: 'That\'s what Extraction tasks are for. Code Execution is for logic that requires precision, not pattern recognition.' },
            { text: 'Summarizing a progress report into bullet points', correct: false, explanation: 'Summarization is a Prompt task \u2014 it\'s language work that LLMs do well.' },
            { text: 'Adding up budget line items or computing percentages from extracted numbers', correct: true, explanation: 'Correct! Math requires precision. LLMs frequently make arithmetic errors, so use Code Execution for any numerical computation.' },
            { text: 'Comparing two documents and identifying differences', correct: false, explanation: 'Document comparison is a Prompt task \u2014 it involves language understanding, which is LLM territory.' },
          ],
        },
      },
      {
        title: 'Running tasks in parallel',
        content: 'Within a single step, you can add multiple tasks. These tasks run concurrently \u2014 the workflow engine uses a thread pool to execute them simultaneously.\n\nThis is useful when you need multiple independent operations:\n\u2022 Extract from two different Extractions at the same time\n\u2022 Call multiple APIs in parallel\n\u2022 Run an extraction while simultaneously fetching enrichment data from a website\n\nTo add parallel tasks, open a step in the workflow editor and click "Add Task" multiple times.',
        variant: 'concept',
        knowledgeCheck: {
          question: 'When you add multiple tasks to a single step, how do they run?',
          options: [
            { text: 'One at a time, in the order you added them', correct: false, explanation: 'Sequential execution would defeat the purpose of parallel tasks. Vandalizer runs them concurrently.' },
            { text: 'Concurrently, using a thread pool', correct: true, explanation: 'Correct! Multiple tasks within a step run in parallel via a thread pool. Their results are collected and passed to the next step.' },
            { text: 'In a random order determined by server load', correct: false, explanation: 'Tasks run concurrently, not in a random order. All start at roughly the same time.' },
            { text: 'Only the first task runs; the rest are treated as fallbacks if it fails', correct: false, explanation: 'All tasks run. There\'s no fallback logic between tasks in a step.' },
          ],
        },
      },
      {
        title: 'Build a workflow with advanced nodes',
        content: '1. Create a workflow with at least 3 steps.\n2. In one step, add a Code Execution task. Write Python that transforms the previous step\'s output.\n3. Or, add an API Call task that fetches data from an external source.\n4. In another step, add 2 tasks to run in parallel.\n5. Run the workflow and review how parallel tasks\' outputs are combined.',
        variant: 'walkthrough',
      },
      {
        title: 'Glossary & Review',
        content: 'Parallel Tasks \u2014 You\'ve now run multiple tasks within a single step concurrently. Their results are collected and passed to the next step together. The benefit: independent operations (two extractions, or an extraction + API call) happen simultaneously instead of sequentially.\n\nCode Execution \u2014 Python in a restricted sandbox with a 10-second timeout. The previous step\'s output is available as `input_data`. Assign your result to `output`. Use for any math, date calculations, or deterministic logic \u2014 never for work that needs language understanding.\n\nAPI Call \u2014 Connects your workflow to external services. Supports GET, POST, PUT, and PATCH. You can pass authentication headers and use the previous step\'s output in the request body \u2014 enabling real-time lookups and integrations.\n\nResearch Node \u2014 Two-stage analysis: first passes through the data to identify patterns, then synthesizes findings into a coherent report. Use when you need more depth than a single Prompt call provides.',
        variant: 'key-terms',
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
        objective: 'After this lesson, you\'ll know which output node to use for different types of deliverables.',
        content: 'So far, your workflows produce text output that you view in the app. But real research administration often requires deliverables: compliance reports to submit, data exports for spreadsheets, or document packages with multiple files.\n\nVandalizer\'s output nodes transform your workflow results into downloadable files:\n\n\u2022 **Document Renderer** \u2014 Generates a markdown or text file from your workflow output.\n\u2022 **Data Export** \u2014 Exports structured data as JSON or CSV.\n\u2022 **Package Builder** \u2014 Creates a ZIP archive containing multiple output files.\n\u2022 **Form Filler** \u2014 Takes a template with placeholders and fills it with extracted data.',
        variant: 'concept',
        knowledgeCheck: {
          question: 'You need to export extracted data from 50 proposals into a spreadsheet. Which output node is the right choice?',
          options: [
            { text: 'Document Renderer \u2014 it produces a formatted text file from workflow output', correct: false, explanation: 'Document Renderer creates a readable document, not structured tabular data. It\'s better for reports you\'d read, not data you\'d analyze in Excel.' },
            { text: 'Package Builder \u2014 it bundles multiple files into a ZIP', correct: false, explanation: 'Package Builder is for collecting multiple output files together, not for producing spreadsheet-compatible data.' },
            { text: 'Data Export \u2014 it converts structured data to CSV or JSON', correct: true, explanation: 'Correct! Data Export with CSV format turns your extracted JSON into columns and rows that open directly in Excel or Google Sheets.' },
            { text: 'Form Filler \u2014 it fills placeholders in a template with extracted values', correct: false, explanation: 'Form Filler is for template-based documents (like filling out a standard form), not for exporting tabular data.' },
          ],
        },
      },
      {
        title: 'Designing end-to-end deliverable workflows',
        content: 'The most powerful workflows go from raw document to finished deliverable in one run:\n\n1. **Extract** \u2014 Pull structured data from the source document.\n2. **Analyze** \u2014 Use Prompt nodes to reason over the data, flag issues, or generate summaries.\n3. **Render** \u2014 Use output nodes to produce the final deliverable.\n\nThe result: upload a grant proposal, click Run, and download a completed compliance checklist.',
        variant: 'concept',
        knowledgeCheck: {
          question: 'What are the three phases of a complete end-to-end deliverable workflow?',
          options: [
            { text: 'Upload, Run, Download', correct: false, explanation: 'Those are UI actions, not the workflow\'s internal phases. The phases describe what the steps do, not what the user does.' },
            { text: 'Extract, Analyze, Render', correct: true, explanation: 'Correct! Extract structured data, analyze or reason over it, then render a deliverable. This maps to the task types: Extraction \u2192 Prompt \u2192 Output node.' },
            { text: 'Prompt, Format, Export', correct: false, explanation: 'Those are task type names, not the three-phase pattern. The pattern is higher-level: Extract \u2192 Analyze \u2192 Render.' },
            { text: 'Parse, Validate, Deliver', correct: false, explanation: 'Parse and Validate aren\'t workflow phases in Vandalizer. The pattern is Extract (get data), Analyze (reason about it), Render (produce output).' },
          ],
        },
      },
      {
        title: 'Build a deliverable workflow',
        content: '1. Start with a workflow that extracts and analyzes data (from Module 3).\n2. Add a new step at the end of your workflow.\n3. Add a Document Renderer or Data Export task to that step.\n4. For Document Renderer: the previous step\'s output will be rendered as a downloadable file.\n5. For Data Export: choose JSON or CSV format.\n6. Run the workflow on a document.\n7. In the results panel, you\'ll see a download link for the generated file.',
        variant: 'walkthrough',
      },
      {
        title: 'Glossary & Review',
        content: 'Document Renderer \u2014 You\'ve now generated downloadable files from workflow output. Document Renderer takes the previous step\'s text and wraps it into a file. Best for reports, summaries, and compliance checklists that people will read.\n\nData Export \u2014 Converts structured JSON data into CSV or JSON files. When using CSV, each extracted key becomes a column header. Best for data that will be loaded into spreadsheets, databases, or other systems.\n\nPackage Builder \u2014 Collects outputs from multiple steps and bundles them into a single ZIP file. Use it when your workflow produces several distinct deliverables that should be distributed together.\n\nForm Filler \u2014 Takes a template string with placeholder syntax and produces a filled-in version using your extracted data. Best when the output must follow a fixed format (like a standard institutional form).\n\nIs Output \u2014 A flag on steps that marks them as output steps. Only steps marked "is_output" contribute to the final downloadable result. Use it to control which steps are deliverables vs. intermediate processing steps.',
        variant: 'key-terms',
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
        objective: 'After this lesson, you\'ll understand why validation is essential before deploying a workflow for production use.',
        content: 'An extraction workflow that works on one document might fail on the next. Different document layouts, writing styles, or terminology can cause the LLM to miss fields or return incorrect values.\n\nValidation lets you define what "correct" looks like for your workflow, test it against sample documents, and track reliability over time.',
        variant: 'concept',
        knowledgeCheck: {
          question: 'What is the primary purpose of a validation plan?',
          options: [
            { text: 'To prevent users from accidentally running a workflow on the wrong document type', correct: false, explanation: 'That\'s a permissions or UI concern. Validation plans are about output quality, not access control.' },
            { text: 'To define what correct output looks like, test it against samples, and track reliability over time', correct: true, explanation: 'Correct! A validation plan defines correctness, tests against known documents, and builds a quality history you can track over time.' },
            { text: 'To automatically fix extraction errors before they reach the user', correct: false, explanation: 'Validation detects problems \u2014 it doesn\'t fix them. You use the results to improve your extraction configuration.' },
            { text: 'To comply with institutional data governance requirements', correct: false, explanation: 'Validation is about workflow quality, not regulatory compliance. It helps you trust your workflow\'s output.' },
          ],
        },
      },
      {
        title: 'Building effective validation plans',
        objective: 'After this lesson, you\'ll be able to design a validation plan that catches the most important failure modes.',
        diagram: 'validation-plan-example',
        content: 'Good validation plans check multiple dimensions of quality:\n\n\u2022 **Completeness** \u2014 Did the workflow extract all expected fields?\n\u2022 **Accuracy** \u2014 Do extracted values match the known-correct values?\n\u2022 **Format** \u2014 Are dates in the right format? Are numbers parsed correctly?\n\u2022 **Consistency** \u2014 When run multiple times, does the workflow produce the same results?\n\nStart with 2-3 high-value checks and expand as you gain confidence.',
        variant: 'concept',
        knowledgeCheck: {
          question: 'A good validation plan checks two foundational dimensions of quality. What are they?',
          options: [
            { text: 'Speed (tokens per second) and cost (dollars per run)', correct: false, explanation: 'Those are performance metrics, not quality dimensions. A fast, cheap workflow that extracts the wrong data is useless.' },
            { text: 'Completeness (all fields extracted) and accuracy (values are correct)', correct: true, explanation: 'Correct! Completeness checks that nothing was missed. Accuracy checks that what was extracted is actually right.' },
            { text: 'Model version and prompt version', correct: false, explanation: 'Those are configuration metadata. Quality checks what the workflow actually produces, not what configuration it uses.' },
            { text: 'Document count and processing time', correct: false, explanation: 'Those are throughput metrics. Validation is about output quality, not volume or speed.' },
          ],
        },
      },
      {
        title: 'Set up validation for your workflow',
        content: '1. Open your workflow in the editor and go to the Validate tab.\n2. Add validation inputs \u2014 paste sample text or select documents.\n3. Create a validation plan with at least 2 quality checks.\n4. Run validation. The system executes your workflow and grades the results.\n5. Review the results: which checks passed, which failed, and why.\n6. Use improvement suggestions to iterate on your extraction.\n7. Check quality history to see how your workflow improves over time.',
        variant: 'walkthrough',
      },
      {
        title: 'Validation as a safety net',
        objective: 'After this lesson, you\'ll understand when to re-run validation and why it should be set up before a workflow goes into production.',
        content: 'The best time to set up validation is before you need it. When you change your Extraction fields, update a prompt, or when the underlying LLM model is updated, your workflow\'s behavior might change. If you have a validation plan, you can re-run it immediately to check for regressions.',
        variant: 'insight',
      },
      {
        title: 'Glossary & Review',
        content: 'Validation Plan \u2014 The definition of "correct" for your workflow. You\'ve now built one: a list of checks that specify what good output looks like. This is what separates a workflow you trust from one you hope works.\n\nValidation Input \u2014 The sample documents or text you test your workflow against. Good validation inputs are representative \u2014 they should reflect the range of documents the workflow will encounter in production.\n\nValidation Run \u2014 An execution of your workflow against validation inputs, automatically graded against your plan. Each run adds a data point to your quality history.\n\nQuality History \u2014 A log of validation run scores over time. This is how you detect regressions: if a score drops after you change a field name or update a model, quality history shows you exactly when.\n\nImprovement Suggestions \u2014 LLM-generated recommendations for improving extraction accuracy based on which checks failed and why. A starting point for iteration, not a final answer.',
        variant: 'key-terms',
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
        objective: 'After this lesson, you\'ll understand when and how to use batch mode for large-scale document processing.',
        content: 'So far you\'ve been running workflows on one document at a time. Batch mode lets you process multiple documents in a single operation.\n\nIn batch mode, the workflow runs once per document, sequentially. Each document gets its own WorkflowResult, and you can monitor progress for the entire batch.\n\nThis is the core value proposition of Vandalizer: define a workflow once, validate it, then run it across hundreds of documents with confidence.',
        variant: 'concept',
        knowledgeCheck: {
          question: 'What does batch mode do that single-document mode doesn\'t?',
          options: [
            { text: 'Uses a more powerful model to produce higher-quality results', correct: false, explanation: 'Batch mode doesn\'t change the model. You can choose any model in either mode.' },
            { text: 'Runs the workflow once per selected document, giving each its own result', correct: true, explanation: 'Correct! Batch mode queues one workflow execution per document. Each run is independent with its own WorkflowResult you can review separately.' },
            { text: 'Skips validation checks to process documents faster', correct: false, explanation: 'Batch mode doesn\'t skip validation. It just applies the workflow across multiple documents automatically.' },
            { text: 'Merges the output of all documents into a single combined result', correct: false, explanation: 'Each document gets its own result. Merging outputs is a workflow design choice, not something batch mode does automatically.' },
          ],
        },
      },
      {
        title: 'Monitoring and debugging batch runs',
        content: 'When running a batch:\n\n\u2022 **Real-time progress** \u2014 The UI shows which document is currently processing.\n\u2022 **Per-document results** \u2014 Each document\'s result is stored independently.\n\u2022 **Error handling** \u2014 Common failures include documents that are too long, unexpected formats, or missing expected fields.\n\nAlways test your workflow on a single document before running a batch.',
        variant: 'concept',
        knowledgeCheck: {
          question: 'What should you always do before running a batch?',
          options: [
            { text: 'Export your workflow as a .vandalizer.json file for backup', correct: false, explanation: 'Exporting is useful for sharing, but not a prerequisite for batch runs.' },
            { text: 'Increase the model\'s context window to handle larger documents', correct: false, explanation: 'Context window is a model property you can\'t configure directly. The right prep step is validating your workflow works on a sample.' },
            { text: 'Test the workflow on a single document first to confirm it works', correct: true, explanation: 'Correct! Always validate with a single document before scaling up. Debugging a batch of 200 failed runs is much harder than fixing one.' },
            { text: 'Create a validation plan with at least 5 checks', correct: false, explanation: 'A validation plan is a good practice, but the essential step is a single-document test run to confirm the workflow produces usable output.' },
          ],
        },
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
      {
        title: 'Glossary & Review',
        content: 'Batch Mode \u2014 You\'ve now run a workflow across multiple documents in one operation. In batch mode, the workflow executes once per document \u2014 each run independent, each result stored separately. This is the core of what makes Vandalizer useful at scale.\n\nBatch ID \u2014 A unique identifier for the batch run. All documents processed in the same batch share this ID, making it easy to find and review the full set of results.\n\nSession ID \u2014 Each individual document execution within a batch has its own session ID. Use it when you need to review or debug a specific document\'s result.\n\nBatch Status \u2014 The aggregated view: how many documents completed successfully, how many failed, and how many are still in progress. Check this to know when your batch is done and whether anything needs reprocessing.',
        variant: 'key-terms',
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
        objective: 'After this lesson, you\'ll understand the three tiers of workflow organization and when to use each.',
        content: 'As your team builds more workflows, organization becomes critical. Use personal work for drafting, then move the workflows your team should reuse into shared team libraries and verified collections.\n\nThink about organization in terms of ownership and audience:\n\u2022 **Personal work** \u2014 early drafts, experiments, and one-off variations.\n\u2022 **Team libraries** \u2014 shared workflows your group actively maintains.\n\u2022 **Verified collections** \u2014 approved workflows that set team standards.',
        variant: 'concept',
      },
      {
        title: 'The verification workflow',
        objective: 'After this lesson, you\'ll understand what "verified" communicates to your team and how to use it as a governance tool.',
        content: 'Marking a workflow as "verified" is a governance practice. It signals to your team that:\n\n1. The workflow has been tested on representative documents.\n2. A validation plan exists and passes consistently.\n3. The output format meets the team\'s requirements.\n4. The workflow is ready for production use.\n\nVerification isn\'t a technical gate \u2014 it\'s a team communication tool.',
        variant: 'concept',
        knowledgeCheck: {
          question: 'What does marking a workflow as "verified" communicate to your team?',
          options: [
            { text: 'The workflow is locked and cannot be edited by other team members', correct: false, explanation: 'Verified is not a lock. It\'s a signal about quality, not a permission restriction.' },
            { text: 'The workflow has been tested, validated, and is approved for production use', correct: true, explanation: 'Correct! Verified is a team communication tool. It says: this workflow has been through quality checks and is ready to rely on.' },
            { text: 'The workflow was created or approved by an admin-level user', correct: false, explanation: 'Any team member can mark a workflow verified. It\'s about the workflow\'s quality, not the creator\'s role.' },
            { text: 'The workflow only uses LLM models approved by your institution', correct: false, explanation: 'Model approval is a separate concern. Verified is about whether the workflow\'s output meets your team\'s quality bar.' },
          ],
        },
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
        knowledgeCheck: {
          question: 'A colleague asks how to verify that budget totals are correct in a workflow. What\'s the right approach?',
          options: [
            { text: 'Write a Prompt node that instructs the LLM to add up the extracted numbers', correct: false, explanation: 'LLMs frequently make arithmetic errors. Never rely on a Prompt node for math \u2014 that\'s Module 2\'s key lesson.' },
            { text: 'Use consensus repetition so three extractions vote on the correct total', correct: false, explanation: 'Consensus repetition improves extraction accuracy, but it won\'t fix arithmetic \u2014 three LLMs making the same math error still agree.' },
            { text: 'Use a Code Execution node after extraction \u2014 code is reliable for math, LLMs aren\'t', correct: true, explanation: 'Correct! This applies the core principle from Module 3: use code for computation, AI for language. Code always gets math right.' },
            { text: 'Extract the numbers and manually verify them after the workflow runs', correct: false, explanation: 'Manual verification defeats the purpose of a workflow. Building the check into the pipeline is the right architectural move.' },
          ],
        },
      },
      {
        title: 'Glossary & Review',
        content: 'Personal work \u2014 Workflows and resources that only you can see and edit. The right place for experiments, drafts, and one-off variations. Graduate your best work to the team context when it\'s ready to share.\n\nVerified \u2014 A governance flag that communicates quality. You\'ve now marked a workflow verified \u2014 that signal tells your team the workflow has been tested, validated, and approved for production use. It\'s a team communication tool, not a technical lock.\n\nExport (.vandalizer.json) \u2014 A portable file containing your workflow\'s complete definition: steps, tasks, field configurations, prompts. It can be imported into any Vandalizer instance and is the standard format for cross-team sharing.\n\nTeam \u2014 A group of users who share access to team workflows, libraries, and folders. Members have roles: owner, admin, or member. Verified workflows in the team context become the standards your whole team builds on.',
        variant: 'key-terms',
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
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const uid = user?.user_id || ''
  const [activeModule, setActiveModuleState] = useState<string | null>(() => {
    try { return localStorage.getItem(`cert-active-module:${uid}`) } catch { return null }
  })
  const setActiveModule = useCallback((id: string | null) => {
    setActiveModuleState(id)
    try { if (id) localStorage.setItem(`cert-active-module:${uid}`, id); else localStorage.removeItem(`cert-active-module:${uid}`) } catch {}
  }, [uid])
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
      // Invalidate document queries so workspace shows the new files without a hard refresh
      queryClient.invalidateQueries({ queryKey: ['documents'] })
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
      localStorage.removeItem(`cert-lesson:${uid}:${completedModuleId}`)
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
