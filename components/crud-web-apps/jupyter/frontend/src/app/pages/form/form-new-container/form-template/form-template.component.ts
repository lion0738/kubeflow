import { Component, EventEmitter, Input, Output } from '@angular/core';
import { ContainerTemplateOption } from 'src/app/types';

@Component({
  selector: 'app-form-template',
  templateUrl: './form-template.component.html',
})
export class FormTemplateComponent {
  @Input() templates: ContainerTemplateOption[] = [];
  @Input() selectedTemplateId = '';

  @Output() templateSelected = new EventEmitter<string>();

  get selectedTemplateDescription(): string {
    if (!this.selectedTemplateId) {
      return '';
    }

    return (
      this.templates.find(template => template.id === this.selectedTemplateId)
        ?.description || ''
    );
  }

  onTemplateSelected(templateId: string) {
    this.templateSelected.emit(templateId);
  }
}
