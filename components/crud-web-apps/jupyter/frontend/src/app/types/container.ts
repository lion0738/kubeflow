import { Status } from 'kubeflow';
import { V1Deployment, V1Pod, V1StatefulSet } from '@kubernetes/client-node';

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
  replicas?: number;
  gpus: {
    count: number;
    message: string;
  };
  volumes: string[];
  status: Status;
  metadata: Record<string, any>;
  workloadKind?: 'Deployment' | 'StatefulSet';
}

export interface ContainerDetail {
  summary: ContainerSummary;
  workload?: V1Deployment | V1StatefulSet;
  workloadKind?: 'Deployment' | 'StatefulSet';
  deployment?: V1Deployment;
  statefulSet?: V1StatefulSet;
  pod?: V1Pod;
  status: Status;
}
