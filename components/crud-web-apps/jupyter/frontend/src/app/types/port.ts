export type PortProtocol = 'TCP' | 'UDP';

export interface PortObject {
  name: string;
  port: number;
  targetPort: number | string;
  nodePort: number;
  protocol: PortProtocol;
  type: string;
}

export interface PortRequest {
  port: number;
  nodePort?: number;
  protocol: PortProtocol;
}
