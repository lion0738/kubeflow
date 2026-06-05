import { Component, OnInit } from '@angular/core';
import { TableColumnComponent } from 'kubeflow/lib/resource-table/component-value/component-value.component';

interface UsedByItem {
  name: string;
  url: string;
}

@Component({
  selector: 'app-used-by',
  templateUrl: './used-by.component.html',
  styleUrls: ['./used-by.component.scss'],
})
export class UsedByComponent implements TableColumnComponent, OnInit {
  public data: any;

  set element(data: any) {
    this.data = data;
  }
  get element() {
    return this.data;
  }

  constructor() {}

  ngOnInit(): void {}

  get pvcName() {
    return this.element.name;
  }

  get usedByItems(): UsedByItem[] {
    return [
      ...(this.element.notebooks || []).map((nb: string) =>
        this.getNotebookUrlItem(nb, this.element),
      ),
      ...(this.element.containers || []).map((container: string) =>
        this.getContainerUrlItem(container, this.element),
      ),
    ];
  }

  getUrlItem(nb: string, element: any) {
    return this.getNotebookUrlItem(nb, element);
  }

  getNotebookUrlItem(nb: string, element: any): UsedByItem {
    return {
      name: nb,
      url: `/jupyter/notebook/details/${element.namespace}/${nb}`,
    };
  }

  getContainerUrlItem(container: string, element: any): UsedByItem {
    return {
      name: container,
      url: `/jupyter/container/details/${element.namespace}/${container}`,
    };
  }
}
