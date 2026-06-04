import { Component, Input, OnChanges, SimpleChanges } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Observable } from 'rxjs';
import {
  SnackBarConfig,
  SnackBarService,
  SnackType,
  STATUS_TYPE,
  Status,
} from 'kubeflow';
import { JWABackendService } from 'src/app/services/backend.service';
import { PortObject, PortProtocol, PortRequest } from 'src/app/types';

@Component({
  selector: 'app-ports',
  templateUrl: './ports.component.html',
  styleUrls: ['./ports.component.scss'],
})
export class PortsComponent implements OnChanges {
  @Input() namespace: string;
  @Input() name: string;
  @Input() isContainer = false;
  @Input() status: Status;

  public ports: PortObject[] = [];
  public loading = false;
  public saving = false;
  public deleting = '';
  public editingServiceName = '';
  public form: FormGroup;

  constructor(
    private fb: FormBuilder,
    private backend: JWABackendService,
    private snackBar: SnackBarService,
  ) {
    this.form = this.fb.group({
      port: [
        '',
        [Validators.required, Validators.min(1), Validators.max(65535)],
      ],
      nodePort: ['', [Validators.min(30000), Validators.max(32767)]],
      protocol: ['TCP', [Validators.required]],
    });
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes.namespace || changes.name || changes.isContainer) {
      this.loadPorts();
    }
  }

  get canEdit(): boolean {
    return this.status?.phase !== STATUS_TYPE.TERMINATING;
  }

  get submitText(): string {
    return this.editingServiceName ? 'UPDATE PORT' : 'ADD PORT';
  }

  public loadPorts(): void {
    if (!this.namespace || !this.name) {
      return;
    }

    this.loading = true;
    this.getPortsRequest().subscribe({
      next: ports => {
        this.ports = ports;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
      },
    });
  }

  public save(): void {
    if (!this.canEdit || this.form.invalid || this.saving) {
      return;
    }

    this.saving = true;
    const isUpdate = Boolean(this.editingServiceName);
    const request = this.editingServiceName
      ? this.updatePortRequest(this.editingServiceName, this.payload())
      : this.createPortRequest(this.payload());

    request.subscribe({
      next: () => {
        const message = isUpdate ? 'Port updated.' : 'Port added.';
        this.snackBar.open(this.snack(message, SnackType.Success));
        this.resetForm();
        this.saving = false;
        this.loadPorts();
      },
      error: () => {
        this.saving = false;
      },
    });
  }

  public edit(port: PortObject): void {
    if (!this.canEdit) {
      return;
    }

    this.editingServiceName = port.name;
    this.form.patchValue({
      port: port.port,
      nodePort: port.nodePort || '',
      protocol: port.protocol,
    });
  }

  public cancelEdit(): void {
    this.resetForm();
  }

  public deletePort(port: PortObject): void {
    if (!this.canEdit || this.deleting) {
      return;
    }

    const confirmed = window.confirm(`Delete port service ${port.name}?`);
    if (!confirmed) {
      return;
    }

    this.deleting = port.name;
    this.deletePortRequest(port.name).subscribe({
      next: () => {
        this.snackBar.open(this.snack('Port deleted.', SnackType.Success));
        if (this.editingServiceName === port.name) {
          this.resetForm();
        }
        this.deleting = '';
        this.loadPorts();
      },
      error: () => {
        this.deleting = '';
      },
    });
  }

  private getPortsRequest(): Observable<PortObject[]> {
    return this.isContainer
      ? this.backend.getContainerPorts(this.namespace, this.name)
      : this.backend.getNotebookPorts(this.namespace, this.name);
  }

  private createPortRequest(port: PortRequest): Observable<PortObject> {
    return this.isContainer
      ? this.backend.createContainerPort(this.namespace, this.name, port)
      : this.backend.createNotebookPort(this.namespace, this.name, port);
  }

  private updatePortRequest(
    serviceName: string,
    port: PortRequest,
  ): Observable<PortObject> {
    return this.isContainer
      ? this.backend.updateContainerPort(
          this.namespace,
          this.name,
          serviceName,
          port,
        )
      : this.backend.updateNotebookPort(
          this.namespace,
          this.name,
          serviceName,
          port,
        );
  }

  private deletePortRequest(serviceName: string): Observable<unknown> {
    return this.isContainer
      ? this.backend.deleteContainerPort(this.namespace, this.name, serviceName)
      : this.backend.deleteNotebookPort(this.namespace, this.name, serviceName);
  }

  private payload(): PortRequest {
    const values = this.form.getRawValue();
    const payload: PortRequest = {
      port: Number(values.port),
      protocol: values.protocol as PortProtocol,
    };

    if (values.nodePort !== null && values.nodePort !== '') {
      payload.nodePort = Number(values.nodePort);
    }

    return payload;
  }

  private resetForm(): void {
    this.editingServiceName = '';
    this.form.reset({
      port: '',
      nodePort: '',
      protocol: 'TCP',
    });
  }

  private snack(msg: string, snackType: SnackType): SnackBarConfig {
    return {
      data: {
        msg,
        snackType,
      },
      duration: 5000,
    };
  }
}
