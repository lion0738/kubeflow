import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';

import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatExpansionModule } from '@angular/material/expansion';

import {
  FormModule as KfFormModule,
  TitleActionsToolbarModule,
} from 'kubeflow';
import { VolumeModule } from './volume/volume.module';
import { FormAdvancedOptionsModule } from './form-advanced-options/form-advanced-options.module';
import { FormAffinityTolerationsModule } from './form-affinity-tolerations/form-affinity-tolerations.module';
import { FormCommandModule } from './form-command/form-command.module';
import { FormCpuRamModule } from './form-cpu-ram/form-cpu-ram.module';
import { FormConfigurationsModule } from './form-configurations/form-configurations.module';
import { FormDataVolumesModule } from './form-data-volumes/form-data-volumes.module';
import { FormGpusModule } from './form-gpus/form-gpus.module';
import { FormImageModule } from './form-image/form-image.module';
import { FormNameModule } from './form-name/form-name.module';
import { FormNewContainerComponent } from './form-new-container.component';

@NgModule({
  declarations: [FormNewContainerComponent],
  imports: [
    CommonModule,
    KfFormModule,
    MatCheckboxModule,
    MatSlideToggleModule,
    MatExpansionModule,
    MatIconModule,
    MatButtonToggleModule,
    TitleActionsToolbarModule,
    VolumeModule,
    FormAdvancedOptionsModule,
    FormAffinityTolerationsModule,
    FormCommandModule,
    FormConfigurationsModule,
    FormCpuRamModule,
    FormDataVolumesModule,
    FormGpusModule,
    FormImageModule,
    FormNameModule,
  ],
  exports: [FormNewContainerComponent],
})
export class FormNewContainerModule {}
