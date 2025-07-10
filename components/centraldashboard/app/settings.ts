export const SECURE_COOKIES =
  (process.env.APP_SECURE_COOKIES || 'true').toLowerCase() === 'true';

export const DISABLE_AUTH =
  (process.env.APP_DISABLE_AUTH || 'false').toLowerCase() === 'true';

export const USER_HEADER = process.env.USERID_HEADER || 'kubeflow-userid';
export const USER_PREFIX = process.env.USERID_PREFIX || ':';
