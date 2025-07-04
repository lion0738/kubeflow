import { FormBuilder, FormGroup, Validators, FormArray } from '@angular/forms';
import { GPU, Config } from 'src/app/types';
import { getNameSyncValidators, getNameAsyncValidators } from 'kubeflow';
import { createFormGroupFromVolume } from 'src/app/shared/utils/volumes';

export function getFormDefaults(): FormGroup {
  const fb = new FormBuilder();

  return fb.group({
    name: ['', [Validators.required]],
    namespace: ['', [Validators.required]],
    imagePullPolicy: ['IfNotPresent', [Validators.required]],
    command: ['/bin/bash -c "sleep infinity"', [Validators.required]],
    customImage: ['', [Validators.required]],
    cpu: [1, [Validators.required]],
    cpuLimit: ['', []],
    memory: [1, [Validators.required]],
    memoryLimit: ['', []],
    gpus: fb.group({
      vendor: ['', []],
      num: ['', []],
    }),
    affinityConfig: ['', []],
    tolerationGroup: ['', []],
    datavols: fb.array([]),
    shm: [true, []],
    configurations: [[], []],
  });
}

export function updateGPUControl(formCtrl: FormGroup, gpuConf: any) {
  // If the backend didn't send the value, default to none
  if (gpuConf == null) {
    formCtrl.get('num').setValue('none');
    return;
  }

  // Set the values
  const gpu = gpuConf.value as GPU;
  formCtrl.get('num').setValue(gpu.num);
  formCtrl.get('vendor').setValue(gpu.vendor);

  // Don't allow the user to edit them if the admin does not allow it
  if (gpuConf.readOnly) {
    formCtrl.get('num').disable();
    formCtrl.get('vendor').disable();
  }
}

export function calculateLimits(
  requests: number | string,
  factor: number | string,
): string | null {
  const limit = configSizeToNumber(requests) * configSizeToNumber(factor);

  if (isNaN(limit)) {
    return null;
  }

  return limit.toFixed(1);
}

export function initCpuFormControls(formCtrl: FormGroup, config: Config) {
  const cpu = Number(config.cpu.value);
  if (!isNaN(cpu)) {
    formCtrl.controls.cpu.setValue(cpu);
  }

  if (config.cpu.readOnly) {
    formCtrl.controls.cpu.disable();
    formCtrl.controls.cpuLimit.disable();
  }

  formCtrl.controls.cpuLimit.setValue(
    calculateLimits(cpu, config.cpu.limitFactor),
  );
}

export function initMemoryFormControls(formCtrl: FormGroup, config: Config) {
  const memory = configSizeToNumber(config.memory.value);
  if (!isNaN(memory)) {
    formCtrl.controls.memory.setValue(memory);
  }

  if (config.memory.readOnly) {
    formCtrl.controls.memory.disable();
    formCtrl.controls.memoryLimit.disable();
  }

  formCtrl.controls.memoryLimit.setValue(
    calculateLimits(memory, config.memory.limitFactor),
  );
}

export function initFormControls(formCtrl: FormGroup, config: Config) {
  initCpuFormControls(formCtrl, config);

  initMemoryFormControls(formCtrl, config);

  formCtrl.controls.imagePullPolicy.setValue(config.imagePullPolicy.value);
  if (config.imagePullPolicy.readOnly) {
    formCtrl.controls.imagePullPolicy.disable();
  }

  // Data volumes
  initDataVolumeControl(formCtrl, config);

  // Affinity
  formCtrl.controls.affinityConfig.setValue(config.affinityConfig.value);
  if (config.affinityConfig.readOnly) {
    formCtrl.controls.affinityConfig.disable();
  }

  // Tolerations
  formCtrl.controls.tolerationGroup.setValue(config.tolerationGroup.value);
  if (config.tolerationGroup.readOnly) {
    formCtrl.controls.tolerationGroup.disable();
  }

  // GPUs
  updateGPUControl(formCtrl.get('gpus') as FormGroup, config.gpus);

  formCtrl.controls.shm.setValue(config.shm.value);
  if (config.shm.readOnly) {
    formCtrl.controls.shm.disable();
  }

  // PodDefaults / Configurations. Set the pre selected labels
  formCtrl.controls.configurations.setValue(config.configurations.value);
  if (config.configurations.readOnly) {
    formCtrl.controls.configurations.disable();
  }
}

export function initDataVolumeControl(form: FormGroup, config: Config) {
  const datavols = config.dataVolumes.value;

  const datavolsArray = new FormArray([]);
  form.setControl('datavols', datavolsArray);

  for (const vol of datavols) {
    datavolsArray.push(createFormGroupFromVolume(vol));
  }
}

export function configSizeToNumber(size: string | number): number {
  if (size == null) {
    return NaN;
  }

  if (typeof size === 'number') {
    return size;
  }

  return Number(size.replace('Gi', ''));
}
