import { Component, Input, OnChanges, SimpleChanges } from '@angular/core';
import { FormArray, FormBuilder, FormGroup, Validators } from '@angular/forms';
import {
  ConfirmDialogService,
  DIALOG_RESP,
  DialogConfig,
  SnackBarConfig,
  SnackBarService,
  SnackType,
  STATUS_TYPE,
  Status,
} from 'kubeflow';
import {
  V1Container,
  V1Pod,
  V1Volume,
  V1VolumeMount,
} from '@kubernetes/client-node';
import { Config, NotebookRawObject } from 'src/app/types';
import { ContainerDetail } from 'src/app/types/container';
import { JWABackendService } from 'src/app/services/backend.service';
import { createFormGroupFromVolume } from 'src/app/shared/utils/volumes';

@Component({
  selector: 'app-settings',
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss'],
})
export class SettingsComponent implements OnChanges {
  @Input() notebook: NotebookRawObject;
  @Input() pod: V1Pod;
  @Input() containerDetail: ContainerDetail;
  @Input() namespace: string;
  @Input() name: string;
  @Input() isContainer = false;
  @Input() notebookStatus: Status;

  config: Config;
  formCtrl: FormGroup;
  saving = false;

  constructor(
    private fb: FormBuilder,
    private backend: JWABackendService,
    private popup: SnackBarService,
    private confirmDialog: ConfirmDialogService,
  ) {
    this.formCtrl = this.fb.group({
      customImage: ['', [Validators.required]],
      imagePullPolicy: ['IfNotPresent', [Validators.required]],
      command: [''],
      cpu: [1, [Validators.required]],
      cpuLimit: [''],
      memory: [1, [Validators.required]],
      memoryLimit: [''],
      replicas: [1, [Validators.required, Validators.min(1)]],
      gpus: this.fb.group({
        vendor: [''],
        num: ['none'],
      }),
      envs: this.fb.array([]),
      datavols: this.fb.array([]),
    });

    this.backend.getConfig().subscribe(config => {
      if (Object.keys(config).length === 0) {
        return;
      }

      this.config = config;
      this.populateForm();
      this.applyGpuConfig();
    });
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (
      changes.notebook ||
      changes.pod ||
      changes.containerDetail ||
      changes.isContainer
    ) {
      this.populateForm();
    }
  }

  get envs(): FormArray {
    return this.formCtrl.get('envs') as FormArray;
  }

  get datavols(): FormArray {
    return this.formCtrl.get('datavols') as FormArray;
  }

  get canSave(): boolean {
    return (
      this.formCtrl.valid &&
      !this.saving &&
      this.notebookStatus?.phase !== STATUS_TYPE.TERMINATING
    );
  }

  save() {
    if (!this.canSave) {
      return;
    }

    const dialogConfig = this.getSaveDialogConfig();
    const ref = this.confirmDialog.open(this.name, dialogConfig);
    const saveSub = ref.componentInstance.applying$.subscribe(applying => {
      if (!applying) {
        return;
      }

      this.applySettings(ref, dialogConfig);
    });

    ref.afterClosed().subscribe(result => {
      saveSub.unsubscribe();
      if (result !== DIALOG_RESP.ACCEPT) {
        this.saving = false;
      }
    });
  }

  private applySettings(ref: any, dialogConfig: DialogConfig) {
    this.saving = true;
    const payload = this.getUpdatePayload();
    const request = this.isContainer
      ? this.backend.updateContainer(this.namespace, this.name, payload)
      : this.backend.updateNotebook(this.namespace, this.name, payload);

    request.subscribe({
      next: () => {
        ref.close(DIALOG_RESP.ACCEPT);
        this.saving = false;
        this.formCtrl.markAsPristine();
        this.popup.open(this.snack('Settings updated.', SnackType.Success));
      },
      error: err => {
        dialogConfig.error = `Error ${err}`;
        ref.componentInstance.applying$.next(false);
        this.saving = false;
      },
    });
  }

  private populateForm() {
    const container = this.getPrimaryContainer();
    if (!container) {
      return;
    }

    const requests = container.resources?.requests || {};
    const limits = container.resources?.limits || {};
    const gpu = this.getGpuValue(limits);

    this.formCtrl.patchValue(
      {
        cpu: this.cpuToCores(requests.cpu) || 1,
        cpuLimit: this.cpuToCores(limits.cpu),
        customImage: container.image || '',
        imagePullPolicy: container.imagePullPolicy || 'IfNotPresent',
        command: this.commandToString(container.command || []),
        memory: this.memoryToGiB(requests.memory) || 1,
        memoryLimit: this.memoryToGiB(limits.memory) || '',
        replicas: this.getReplicas(),
        gpus: gpu,
      },
      { emitEvent: false },
    );
    this.applyGpuConfig();

    this.envs.clear();
    for (const env of container.env || []) {
      if (!env.name || env.value === undefined) {
        continue;
      }

      this.envs.push(
        this.fb.group({
          name: [env.name, [Validators.required]],
          value: [env.value || ''],
        }),
      );
    }

    this.datavols.clear();
    for (const volume of this.getPvcFormVolumes()) {
      this.datavols.push(createFormGroupFromVolume(volume));
    }

    this.formCtrl.markAsPristine();
  }

  private getUpdatePayload() {
    const values = this.formCtrl.getRawValue();
    const limits = this.getPreservedLimits();
    const requests = {
      cpu: this.normalizeCpu(values.cpu),
      memory: this.toGi(values.memory),
    };

    if (values.cpuLimit !== null && values.cpuLimit !== '') {
      limits['cpu'] = this.normalizeCpu(values.cpuLimit);
    }

    if (values.memoryLimit !== null && values.memoryLimit !== '') {
      limits['memory'] = this.toGi(values.memoryLimit);
    }

    if (values.gpus?.num && values.gpus.num !== 'none') {
      limits[values.gpus.vendor] = values.gpus.num.toString();
    }

    const payload: Record<string, unknown> = {
      resources: {
        requests,
        limits,
      },
      image: values.customImage?.trim(),
      imagePullPolicy: values.imagePullPolicy,
      datavols: values.datavols,
    };

    if (this.isContainer) {
      payload.command = values.command || '';
      payload.replicas = Math.max(1, Number(values.replicas));
      payload.envs = values.envs
        .filter(env => env.name)
        .map(env => ({
          name: env.name,
          value: env.value || '',
        }));
    }

    return payload;
  }

  private getPrimaryContainer(): V1Container {
    if (this.isContainer) {
      return this.containerDetail?.deployment?.spec?.template?.spec
        ?.containers?.[0];
    }

    return (
      this.pod?.spec?.containers?.[0] ||
      this.notebook?.spec?.template?.spec?.containers?.[0]
    );
  }

  private getReplicas(): number {
    if (!this.isContainer) {
      return 1;
    }

    return (
      this.containerDetail?.deployment?.spec?.replicas ||
      this.containerDetail?.summary?.replicas ||
      1
    );
  }

  private getPodSpec() {
    if (this.isContainer) {
      return this.containerDetail?.deployment?.spec?.template?.spec;
    }

    return this.notebook?.spec?.template?.spec || this.pod?.spec;
  }

  private getPvcFormVolumes() {
    const podSpec = this.getPodSpec();
    const container = this.getPrimaryContainer();
    const volumes = podSpec?.volumes || [];
    const mounts = container?.volumeMounts || [];
    const mountByName = new Map<string, V1VolumeMount>();

    for (const mount of mounts) {
      mountByName.set(mount.name, mount);
    }

    return volumes
      .filter((volume: V1Volume) => volume.persistentVolumeClaim)
      .filter((volume: V1Volume) => mountByName.has(volume.name))
      .map((volume: V1Volume) => {
        const mount = mountByName.get(volume.name);
        return {
          name: volume.name,
          mount: mount?.mountPath || '',
          existingSource: {
            name: volume.name,
            persistentVolumeClaim: volume.persistentVolumeClaim,
          },
        };
      });
  }

  private getGpuValue(limits: Record<string, string>) {
    const defaultGpu = this.getDefaultGpuValue();
    if (this.config?.gpus?.readOnly) {
      return defaultGpu;
    }

    if (!limits || !this.config?.gpus?.value?.vendors) {
      return defaultGpu;
    }

    for (const vendor of this.config.gpus.value.vendors) {
      const value = limits[vendor.limitsKey];
      if (value) {
        return { vendor: vendor.limitsKey, num: value.toString() };
      }
    }

    return defaultGpu;
  }

  private applyGpuConfig() {
    const gpuCtrl = this.formCtrl.get('gpus') as FormGroup;
    if (!this.config?.gpus?.readOnly) {
      gpuCtrl.enable({ emitEvent: false });
      return;
    }

    gpuCtrl.patchValue(this.getDefaultGpuValue(), { emitEvent: false });
    gpuCtrl.disable({ emitEvent: false });
  }

  private getDefaultGpuValue() {
    const gpu = this.config?.gpus?.value;
    return {
      vendor: gpu?.vendor || '',
      num: gpu?.num || 'none',
    };
  }

  private getPreservedLimits(): Record<string, string> {
    const container = this.getPrimaryContainer();
    const currentLimits = container?.resources?.limits || {};
    const preserved = {};
    const managedKeys = new Set(['cpu', 'memory']);

    for (const vendor of this.config?.gpus?.value?.vendors || []) {
      managedKeys.add(vendor.limitsKey);
    }

    for (const key of Object.keys(currentLimits)) {
      if (!managedKeys.has(key)) {
        preserved[key] = currentLimits[key].toString();
      }
    }

    return preserved;
  }

  private memoryToGiB(memory: string): string | number {
    if (!memory) {
      return '';
    }

    const normalized = memory.toString().replace(/\s+/g, '');
    if (normalized.endsWith('Gi')) {
      return Number(normalized.replace(/Gi$/, ''));
    }

    if (normalized.endsWith('Mi')) {
      return Number(normalized.replace(/Mi$/, '')) / 1024;
    }

    const parsed = Number(normalized);
    return isNaN(parsed) ? normalized : parsed;
  }

  private toGi(value: string | number): string {
    const stringValue = value?.toString().replace(/\s+/g, '') || '';
    return stringValue.endsWith('Gi') ? stringValue : `${stringValue}Gi`;
  }

  private cpuToCores(cpu: string | number): string | number {
    if (cpu === null || cpu === undefined || cpu === '') {
      return '';
    }

    const normalized = cpu.toString().replace(/\s+/g, '');
    if (normalized.endsWith('m')) {
      const milliCpu = Number(normalized.replace(/m$/, ''));
      return isNaN(milliCpu) ? normalized : milliCpu / 1000;
    }

    const parsed = Number(normalized);
    return isNaN(parsed) ? normalized : parsed;
  }

  private normalizeCpu(cpu: string | number): string {
    return this.cpuToCores(cpu).toString();
  }

  private commandToString(command: string[]): string {
    return command.map(arg => this.shellQuoteArg(arg)).join(' ');
  }

  private shellQuoteArg(arg: string): string {
    const value = arg?.toString() || '';
    if (value === '') {
      return "''";
    }

    if (!/[\s'"]/g.test(value)) {
      return value;
    }

    return "'" + value.replace(/'/g, "'\\''") + "'";
  }

  private getSaveDialogConfig(): DialogConfig {
    return {
      title: $localize`Save settings for ${this.name}?`,
      message: $localize`Warning: Saving these settings will restart the container. Active sessions and running processes may be interrupted.`,
      accept: $localize`SAVE`,
      confirmColor: 'primary',
      cancel: $localize`CANCEL`,
      error: '',
      applying: $localize`SAVING`,
      width: '600px',
    };
  }

  private snack(msg: string, snackType: SnackType): SnackBarConfig {
    return {
      data: {
        msg,
        snackType,
      },
    };
  }
}
