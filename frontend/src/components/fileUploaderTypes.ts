const DOCUMENT_FILE_TYPES = [
  'pdf',
  'docx',
  'xlsx',
  'xls',
  'txt',
  'jpg',
  'png',
  'csv',
  'html',
] as const

const VIDEO_FILE_TYPE_VALUES = ['mp4', 'mov', 'avi', 'mkv', 'webm'] as const

export type FileType =
  | (typeof DOCUMENT_FILE_TYPES)[number]
  | (typeof VIDEO_FILE_TYPE_VALUES)[number]

interface FileTypeInfo {
  label: string
  accept: string[]
  extensions: string[]
}

export const FILE_TYPE_OPTIONS: Record<FileType, FileTypeInfo> = {
  pdf: {
    label: 'PDF',
    accept: ['.pdf', 'application/pdf'],
    extensions: ['pdf'],
  },
  docx: {
    label: 'DOCX',
    accept: [
      '.docx',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    ],
    extensions: ['docx'],
  },
  xlsx: {
    label: 'XLSX',
    accept: [
      '.xlsx',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    ],
    extensions: ['xlsx'],
  },
  xls: {
    label: 'XLS',
    accept: ['.xls', 'application/vnd.ms-excel'],
    extensions: ['xls'],
  },
  txt: {
    label: 'TXT',
    accept: ['.txt', 'text/plain'],
    extensions: ['txt'],
  },
  jpg: {
    label: 'JPG/JPEG',
    accept: ['.jpg', '.jpeg', 'image/jpeg'],
    extensions: ['jpg', 'jpeg'],
  },
  png: {
    label: 'PNG',
    accept: ['.png', 'image/png'],
    extensions: ['png'],
  },
  csv: {
    label: 'CSV',
    accept: ['.csv', 'text/csv'],
    extensions: ['csv'],
  },
  html: {
    label: 'HTML',
    accept: ['.html', '.htm', 'text/html'],
    extensions: ['html', 'htm'],
  },
  mp4: {
    label: 'MP4',
    accept: ['.mp4', 'video/mp4'],
    extensions: ['mp4'],
  },
  mov: {
    label: 'MOV',
    accept: ['.mov', 'video/quicktime'],
    extensions: ['mov'],
  },
  avi: {
    label: 'AVI',
    accept: ['.avi', 'video/x-msvideo'],
    extensions: ['avi'],
  },
  mkv: {
    label: 'MKV',
    accept: ['.mkv', 'video/x-matroska'],
    extensions: ['mkv'],
  },
  webm: {
    label: 'WEBM',
    accept: ['.webm', 'video/webm'],
    extensions: ['webm'],
  },
}

export const ALL_FILE_TYPES = [...DOCUMENT_FILE_TYPES] as FileType[]

export const VIDEO_FILE_TYPES = [...VIDEO_FILE_TYPE_VALUES] as FileType[]
