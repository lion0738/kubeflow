export type PortProtocol = 'TCP' | 'UDP';
export type PortAccessType = 'NodePort' | 'Gateway';

export interface PortEndpoint {
  serviceName: string;
  nodePort?: number;
  podName?: string;
  hostname?: string;
  url?: string;
}

export interface PortObject {
  name: string;
  port: number;
  targetPort: number | string;
  nodePort?: number;
  protocol: PortProtocol;
  type: string;
  accessType?: PortAccessType;
  domain?: string;
  perReplica: boolean;
  endpoints: PortEndpoint[];
}

export interface PortRequest {
  port: number;
  nodePort?: number;
  protocol: PortProtocol;
  accessType?: PortAccessType;
  domain?: string;
  perReplica?: boolean;
}
