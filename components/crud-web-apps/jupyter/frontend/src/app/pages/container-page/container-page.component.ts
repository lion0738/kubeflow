import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { JWABackendService } from 'src/app/services/backend.service';

@Component({
  selector: 'app-container-log-page',
  templateUrl: './container-page.component.html',
  styleUrls: ['./container-page.component.scss'],
})
export class ContainerLogPageComponent implements OnInit {
  logs = '';
  loading = true;
  error = '';

  constructor(
    private route: ActivatedRoute,
    private backend: JWABackendService,
  ) {}

  ngOnInit(): void {
    const namespace = this.route.snapshot.paramMap.get('namespace');
    const name = this.route.snapshot.paramMap.get('name');

    if (!namespace || !name) {
      this.error = 'Invalid route parameters.';
      this.loading = false;
      return;
    }

    this.backend.getPod(namespace, `app=${name}`).subscribe({
      next: pods => {
        const podName = pods?.metadata?.name;
        if (!podName) {
          this.error = 'No matching pod found.';
          this.loading = false;
          return;
        }

        this.backend.getContainerLogs(namespace, podName, name).subscribe({
          next: logs => {
            this.logs = logs;
            this.loading = false;
          },
          error: () => {
            this.error = 'Failed to fetch logs.';
            this.loading = false;
          },
        });
      },
      error: () => {
        this.error = 'Failed to fetch pod list.';
        this.loading = false;
      },
    });
  }
}
