import { ActionConfig } from './action';

export interface ActionButtonConfig extends ActionConfig {
  text: string;
  loadingField?: string;
}

export class ActionButtonValue {
  name: string;
  tooltip: string;
  color: string;
  field: string;
  text: string;
  loadingField: string;

  private defaultValues: ActionButtonConfig = {
    name: '',
    tooltip: '',
    color: '',
    field: '',
    text: '',
    loadingField: '',
  };

  constructor(config: ActionButtonConfig) {
    const { name, tooltip, color, field, text, loadingField } = {
      ...this.defaultValues,
      ...config,
    };

    this.name = name;
    this.tooltip = tooltip;
    this.color = color;
    this.field = field;
    this.text = text;
    this.loadingField = loadingField;
  }
}
