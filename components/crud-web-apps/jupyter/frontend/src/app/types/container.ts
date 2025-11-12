import { Status } from 'kubeflow';
import { V1Deployment, V1Pod } from '@kubernetes/client-node';

export interface ContainerSummary {
  name: string;
  namespace: string;
  owner?: string;
  ip?: string;
  serverType: 'container';
  age: string;
  last_activity?: string;
  image: string;
  shortImage: string;
  cpu?: string;
  memory?: string;
  gpus: {
    count: number;
    message: string;
  };
  volumes: string[];
  status: Status;
  metadata: Record<string, any>;
}

export interface ContainerDetail {
  summary: ContainerSummary;
  deployment: V1Deployment;
  pod?: V1Pod;
  status: Status;
}
