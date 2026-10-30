/** Graph intake is managed separately and is not connected by creating an Automation. */
export function Microsoft365IntakeGuide({ existing = false }: { existing?: boolean }) {
  return <div className="automation-intake-guide">
    <strong>{existing ? 'Check your Microsoft 365 connection' : 'Microsoft 365 needs separate setup'}</strong>
    <p>Connecting a mailbox or OneDrive source is managed by your administrator. Creating or enabling an automation here does not connect that source.</p>
    <ol>
      <li>Ask your administrator to confirm the connected mailbox or OneDrive folder.</li>
      <li>Confirm which saved workflow receives its incoming documents.</li>
    </ol>
    <p>For documents already arriving in a Vandalizer folder, choose <strong>Folder Watch</strong> and select that folder.</p>
    {existing && <p><strong>Run now</strong> lets you choose documents for a one-off run. It does not test the Microsoft 365 connection.</p>}
  </div>
}
