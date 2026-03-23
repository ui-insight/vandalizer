export interface SupportMessage {
  uuid: string
  user_id: string
  user_name: string | null
  content: string
  is_support_reply: boolean
  created_at: string | null
}

export interface SupportAttachment {
  uuid: string
  filename: string
  file_type: string | null
  uploaded_by: string
  message_uuid: string | null
  created_at: string | null
}

export interface SupportTicket {
  uuid: string
  subject: string
  status: 'open' | 'in_progress' | 'closed'
  priority: 'low' | 'normal' | 'high'
  user_id: string
  user_name: string | null
  user_email: string | null
  team_id: string | null
  assigned_to: string | null
  messages: SupportMessage[]
  attachments: SupportAttachment[]
  message_count: number
  created_at: string | null
  updated_at: string | null
  closed_at: string | null
}

export interface SupportTicketSummary {
  uuid: string
  subject: string
  status: 'open' | 'in_progress' | 'closed'
  priority: 'low' | 'normal' | 'high'
  user_id: string
  user_name: string | null
  assigned_to: string | null
  message_count: number
  last_message_preview: string | null
  last_message_at: string | null
  created_at: string | null
  updated_at: string | null
  closed_at: string | null
}

export interface SupportContact {
  user_id: string
  email: string
  name: string
}
