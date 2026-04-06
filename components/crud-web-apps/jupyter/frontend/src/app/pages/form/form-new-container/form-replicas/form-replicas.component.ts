import { Component, Input } from '@angular/core';
import { FormGroup } from '@angular/forms';

@Component({
  selector: 'app-form-replicas',
  templateUrl: './form-replicas.component.html',
})
export class FormReplicasComponent {
  @Input() parentForm: FormGroup;
}
