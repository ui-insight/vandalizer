const labels: Record<string, string> = {
  Extraction: 'Extract fields', Prompt: 'Prompt', Formatter: 'Format output', Format: 'Format output',
  AddDocument: 'Add document', AddWebsite: 'Read a web page', CrawlerNode: 'Crawl a website',
  ResearchNode: 'Deep analysis', KnowledgeBaseQuery: 'Ask a knowledge base', APINode: 'Call an API',
  DocumentRenderer: 'Create a document', FormFiller: 'Fill a form', DataExport: 'Export data',
  Approval: 'Request approval', Browser: 'Browser automation', DescribeImage: 'Describe an image',
  CodeNode: 'Run code', PackageBuilder: 'Build a package',
}

export function workflowTaskLabel(type: string): string { return labels[type] ?? type }
export function workflowTaskTitle(task: { name: string; data?: Record<string, unknown> }): string {
  return typeof task.data?.name === 'string' && task.data.name.trim() ? task.data.name : workflowTaskLabel(task.name)
}
