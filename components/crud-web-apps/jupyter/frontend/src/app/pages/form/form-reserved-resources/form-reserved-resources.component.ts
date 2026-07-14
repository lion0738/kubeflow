import { Component, Input, OnChanges, OnDestroy } from '@angular/core';
import { Subscription } from 'rxjs';
import { JWABackendService } from 'src/app/services/backend.service';
import { ReservedResourceAvailability } from 'src/app/types';

@Component({
  selector: 'app-form-reserved-resources',
  templateUrl: './form-reserved-resources.component.html',
  styleUrls: ['./form-reserved-resources.component.scss'],
})
export class FormReservedResourcesComponent implements OnChanges, OnDestroy {
  @Input() namespace = '';

  resources: ReservedResourceAvailability[] = [];
  loading = false;
  loadError = false;

  private resourceSubscription?: Subscription;

  constructor(private backend: JWABackendService) {}

  ngOnChanges(): void {
    this.loadResources();
  }

  ngOnDestroy(): void {
    this.resourceSubscription?.unsubscribe();
  }

  private loadResources(): void {
    this.resourceSubscription?.unsubscribe();
    this.resources = [];
    this.loadError = false;

    if (!this.namespace) {
      this.loading = false;
      return;
    }

    this.loading = true;
    this.resourceSubscription = this.backend
      .getReservedResourceAvailability(this.namespace)
      .subscribe({
        next: resources => {
          this.resources = resources.map(resource => ({
            ...resource,
            remaining_cpu_count: Math.max(0, resource.remaining_cpu_count),
            remaining_gpu_count: Math.max(0, resource.remaining_gpu_count),
            remaining_memory_size: Math.max(0, resource.remaining_memory_size),
          }));
          this.loading = false;
        },
        error: () => {
          this.loadError = true;
          this.loading = false;
        },
      });
  }
}
