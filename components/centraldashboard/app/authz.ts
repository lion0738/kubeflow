import * as k8s from '@kubernetes/client-node';
import { Request } from 'express';
import { getUsername } from './authn';
import { DISABLE_AUTH } from './settings';
import { Forbidden } from 'http-errors';

const kc = new k8s.KubeConfig();
kc.loadFromDefault();
const authzApi = kc.makeApiClient(k8s.AuthorizationV1Api);

// SubjectAccessReview 요청 객체 생성
function createSubjectAccessReview(
  user: string,
  verb: string,
  group: string,
  version: string,
  resource: string,
  namespace?: string,
  subresource?: string
): k8s.V1SubjectAccessReview {
  return {
    apiVersion: 'authorization.k8s.io/v1',
    kind: 'SubjectAccessReview',
    spec: {
      user,
      resourceAttributes: {
        namespace,
        verb,
        group,
        version,
        resource,
        subresource,
      },
    },
  };
}

// 권한 확인 함수
export async function ensureAuthorized(
  req: Request,
  verb: string,
  group: string,
  version: string,
  resource: string,
  namespace?: string,
  subresource?: string
): Promise<void> {
  if (DISABLE_AUTH) return;

  const user = getUsername(req);
  if (!user) {
    throw new Forbidden('No user identity found in request');
  }

  const sar = createSubjectAccessReview(user, verb, group, version, resource, namespace, subresource);

  try {
    const res = await authzApi.createSubjectAccessReview(sar);
    if (!res.body.status?.allowed) {
      const msg = `User '${user}' is not authorized to ${verb} ${group}/${version}/${resource} ${namespace ? `in namespace '${namespace}'` : ''}`;
      throw new Forbidden(msg);
    }
  } catch (err) {
    console.error('Error during SubjectAccessReview:', err);
    throw new Forbidden('Authorization failed');
  }
}
