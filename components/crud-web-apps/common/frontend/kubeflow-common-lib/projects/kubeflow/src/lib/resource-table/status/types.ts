export enum STATUS_TYPE {
  READY = 'ready',
  DOWNLOADING = 'downloading',
  WAITING = 'waiting',
  WARNING = 'warning',
  ERROR = 'error',
  UNAVAILABLE = 'unavailable',
  UNINITIALIZED = 'uninitialized',
  TERMINATING = 'terminating',
  STOPPED = 'stopped',
}

export interface Status {
  phase: STATUS_TYPE;
  state: string;
  message: string;
}
