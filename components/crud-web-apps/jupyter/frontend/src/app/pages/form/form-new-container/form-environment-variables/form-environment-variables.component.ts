import { Component, Input } from '@angular/core';
import { FormArray, FormBuilder, Validators } from '@angular/forms';

@Component({
  selector: 'app-form-environment-variables',
  templateUrl: './form-environment-variables.component.html',
  styleUrls: ['./form-environment-variables.component.scss'],
})
export class FormEnvironmentVariablesComponent {
  @Input() envsArray: FormArray;

  constructor(private fb: FormBuilder) {}

  addEnv() {
    this.envsArray.push(
      this.fb.group({
        name: ['', [Validators.required]],
        value: [''],
      }),
    );
  }

  removeEnv(i: number) {
    this.envsArray.removeAt(i);
  }
}
