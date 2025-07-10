import { Request } from 'express';
import { USER_HEADER, USER_PREFIX } from './settings';

export function getUsername(req: Request): string | null {
  const rawUser = req.headers[USER_HEADER.toLowerCase()];
  if (!rawUser || typeof rawUser !== 'string') {
    console.debug("User header not present!");
    return null;
  }

  const username = rawUser.replace(USER_PREFIX, '');
  console.debug(`User: '${username}' | Headers: '${USER_HEADER}' '${USER_PREFIX}'`);
  return username;
}
