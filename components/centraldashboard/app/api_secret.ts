import {Router, Request, Response} from 'express';
import {KubernetesService} from './k8s_service';
import {apiError} from './api';
import * as k8s from '@kubernetes/client-node';

interface CreateSecretRequest {
  namespace: string;
  name: string;
  registry: string;
  username: string;
  password: string;
  email: string;
}

export class SecretApi {
  constructor(private k8sService: KubernetesService) {}

  routes() {
    return Router()
      // Create docker-registry secret and update PodDefault
      .post('/create', async (req: Request, res: Response) => {
        const {namespace, name, registry, username, password, email} = req.body as CreateSecretRequest;

        if (!namespace || !name || !registry || !username || !password || !email) {
          return apiError({res, code: 400, error: 'Missing required fields'});
        }

        try {
          await this.k8sService.createDockerRegistrySecret(namespace, name, registry, username, password, email);
          await this.k8sService.upsertPodDefaultWithSecrets(namespace);
          res.json({message: `Secret ${name} created and PodDefault updated in namespace ${namespace}`});
        } catch (err) {
          apiError({res, code: 500, error: `Failed to create secret or update PodDefault: ${err.body?.message || err.message}`});
        }
      })

      // List dockerconfigjson secrets
      .get('/list/:namespace', async (req: Request, res: Response) => {
        const namespace = req.params.namespace;
        try {
          const secrets = await this.k8sService.listDockerRegistrySecrets(namespace);
          res.json(secrets);
        } catch (err) {
          apiError({res, code: 500, error: `Failed to list secrets: ${err.body?.message || err.message}`});
        }
      })

      // Delete secret and update PodDefault
      .delete('/delete/:namespace/:name', async (req: Request, res: Response) => {
        const {namespace, name} = req.params;
        try {
          await this.k8sService.deleteDockerRegistrySecret(namespace, name);
          await this.k8sService.upsertPodDefaultWithSecrets(namespace);
          res.json({message: `Secret ${name} deleted and PodDefault updated in namespace ${namespace}`});
        } catch (err) {
          apiError({res, code: 500, error: `Failed to delete secret or update PodDefault: ${err.body?.message || err.message}`});
        }
      });
  }
}
