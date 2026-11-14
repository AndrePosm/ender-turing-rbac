import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"

import { MetricsService } from "@/client"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { requirePermission } from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/metrics")({
  component: Metrics,
  beforeLoad: ({ context, preload }) =>
    requirePermission(context.queryClient, "metrics:read", preload),
  head: () => ({
    meta: [{ title: "Metrics - FastAPI Template" }],
  }),
})

function Metrics() {
  const { data } = useQuery({
    queryKey: ["metrics"],
    queryFn: async () => (await MetricsService.readMetrics()).data,
  })

  const stats = [
    { label: "Total users", value: data?.total_users },
    { label: "Active users", value: data?.active_users },
    { label: "Admins", value: data?.users_by_role.admin ?? 0 },
    { label: "Managers", value: data?.users_by_role.manager ?? 0 },
    { label: "Members", value: data?.users_by_role.member ?? 0 },
    { label: "Items", value: data?.total_items },
  ]

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Metrics</h1>
        <p className="text-muted-foreground">Basic usage overview</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {stats.map((stat) => (
          <Card key={stat.label}>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {stat.label}
              </CardTitle>
            </CardHeader>
            <CardContent className="text-2xl font-bold">
              {data ? stat.value : "–"}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
