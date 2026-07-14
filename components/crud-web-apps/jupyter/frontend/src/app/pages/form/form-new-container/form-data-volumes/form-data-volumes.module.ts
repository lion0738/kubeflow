import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormModule as KfFormModule } from 'kubeflow';
import { FormDataVolumesComponent } from './form-data-volumes.component';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { ReactiveFormsModule } from '@angular/forms';
import { VolumeModule } from '../volume/volume.module';

@NgModule({
  declarations: [FormDataVolumesComponent],
  imports: [
    CommonModule,
    KfFormModule,
    MatExpansionModule,
    MatIconModule,
    MatButtonToggleModule,
    MatSlideToggleModule,
    ReactiveFormsModule,
    VolumeModule,
  ],
  exports: [FormDataVolumesComponent],
})
export class FormDataVolumesModule {}
