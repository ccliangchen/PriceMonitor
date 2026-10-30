export interface Health {
  status: 'ok'
  version: string
  uptime_seconds: number
  data_dir: string
  database: 'ok' | 'error'
}

export type NotificationChannel = 'serverchan' | 'pushplus'

export interface AppSettings {
  poll_interval_minutes: number
  checkout_interval_hours: number
  close_to_tray: boolean
  auto_start: boolean
  notification_channel: NotificationChannel
  history_retention_days: number
}
