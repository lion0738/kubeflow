import { CommonModule } from '@angular/common';
import { NgModule } from '@angular/core';
import { ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { FormCpuRamModule } from '../../form/form-new/form-cpu-ram/form-cpu-ram.module';
import { FormGpusModule } from '../../form/form-new/form-gpus/form-gpus.module';
import { FormCommandModule } from '../../form/form-new-container/form-command/form-command.module';
import { FormDataVolumesModule } from '../../form/form-new-container/form-data-volumes/form-data-volumes.module';
import { FormEnvironmentVariablesModule } from '../../form/form-new-container/form-environment-variables/form-environment-variables.module';
import { FormImageModule } from '../../form/form-new-container/form-image/form-image.module';
import { FormReplicasModule } from '../../form/form-new-container/form-replicas/form-replicas.module';
import { SettingsComponent } from './settings.component';

@NgModule({
  declarations: [SettingsComponent],
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatButtonModule,
    FormCommandModule,
    FormCpuRamModule,
    FormDataVolumesModule,
    FormEnvironmentVariablesModule,
    FormGpusModule,
    FormImageModule,
    FormReplicasModule,
  ],
  exports: [SettingsComponent],
})
export class SettingsModule {}
