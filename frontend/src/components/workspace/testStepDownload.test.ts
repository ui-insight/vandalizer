import { describe, it, expect } from 'vitest'
import { planTestResultDownload } from './WorkflowEditorPanel'

// What reaches the client is the return of the engine's _format_final_output:
// a string in every case *except* a {type: "file_download"} payload, which is
// passed through as an object. Splitting on "is it a string?" therefore gets
// both cases backwards, which is what these cover.

describe('planTestResultDownload', () => {
  it('decodes a file-producing step to its real file, not a JSON blob of base64', () => {
    // DocumentRenderer / DataExport / PackageBuilder steps are all testable and
    // all return this shape. Saving it as JSON hands the user megabytes of
    // base64 named .json instead of the .docx they rendered.
    const plan = planTestResultDownload(
      {
        type: 'file_download',
        data_b64: 'cHduZWQ=',
        file_type: 'docx',
        filename: 'report.docx',
      },
      'Render report',
    )

    expect(plan).not.toBeNull()
    expect(plan!.kind).toBe('file')
    expect(plan!.filename).toBe('report.docx')
    expect(plan!.content).toBe('cHduZWQ=')
    expect(plan!.mime).toBe('application/octet-stream')
  })

  it('falls back to a step-named file when the payload carries no filename', () => {
    const plan = planTestResultDownload(
      { type: 'file_download', data_b64: 'AAA=' },
      'Build package',
    )
    expect(plan!.filename).toBe('Build_package-test.bin')
  })

  it('gives already-serialized JSON a .json extension', () => {
    // Structured results are json.dumps'd server-side, so they arrive as a
    // *string* — the old split wrote them as .txt and they would not open in
    // JSON tooling by extension.
    const plan = planTestResultDownload('{\n  "total": 3\n}', 'Extract fields')
    expect(plan!.kind).toBe('json')
    expect(plan!.filename).toBe('Extract_fields-test.json')
    expect(plan!.mime).toBe('application/json')
  })

  it('leaves prose as .txt', () => {
    const plan = planTestResultDownload('The recipient shall retain records.', 'Summarize')
    expect(plan!.kind).toBe('text')
    expect(plan!.filename).toBe('Summarize-test.txt')
    expect(plan!.mime).toBe('text/plain')
  })

  it('does not mistake prose that merely starts with a brace for JSON', () => {
    const plan = planTestResultDownload('{not json at all', 'Summarize')
    expect(plan!.kind).toBe('text')
    expect(plan!.filename).toBe('Summarize-test.txt')
  })

  it('names the file after the label the user sees, not the node type', () => {
    // Three differently-named Prompt steps all download as Prompt-test.txt
    // otherwise, and repeated saves become "Prompt-test (1).txt".
    const a = planTestResultDownload('out', 'Draft cover letter')
    const b = planTestResultDownload('out', 'Draft budget note')
    expect(a!.filename).toBe('Draft_cover_letter-test.txt')
    expect(b!.filename).toBe('Draft_budget_note-test.txt')
    expect(a!.filename).not.toBe(b!.filename)
  })

  it('has nothing to offer for an absent or empty result', () => {
    // _format_final_output(None) returns "", and the Test Completed block still
    // renders — downloading would write a 0-byte file.
    expect(planTestResultDownload(null, 'Step')).toBeNull()
    expect(planTestResultDownload(undefined, 'Step')).toBeNull()
    expect(planTestResultDownload('', 'Step')).toBeNull()
  })

  it('survives a label made entirely of punctuation', () => {
    const plan = planTestResultDownload('out', '///')
    expect(plan!.filename).toBe('step-test.txt')
  })
})
