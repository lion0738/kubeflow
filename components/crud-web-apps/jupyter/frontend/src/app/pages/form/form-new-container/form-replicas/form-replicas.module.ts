import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { FormModule as KfFormModule } from 'kubeflow';
import { FormReplicasComponent } from './form-replicas.component';

@NgModule({
  declarations: [FormReplicasComponent],
  imports: [
    CommonModule,
    KfFormModule,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatInputModule,
  ],
  exports: [FormReplicasComponent],
})
export class FormReplicasModule {}
