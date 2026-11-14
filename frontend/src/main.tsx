import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query"
import { createRouter, RouterProvider } from "@tanstack/react-router"
import { AxiosError } from "axios"
import { StrictMode } from "react"
import ReactDOM from "react-dom/client"
import { client } from "./client/client.gen"
import { ThemeProvider } from "./components/theme-provider"
import { Toaster } from "./components/ui/sonner"
import "./index.css"
import { routeTree } from "./routeTree.gen"

client.setConfig({
  baseURL: import.meta.env.VITE_API_URL ?? "",
  auth: () => localStorage.getItem("access_token") || "",
})

const handleApiError = (error: Error) => {
  if (!(error instanceof AxiosError)) return
  const status = error.response?.status
  if (status === 401) {
    // Session is no longer valid (expired, deactivated or deleted user).
    localStorage.removeItem("access_token")
    queryClient.clear()
    if (window.location.pathname !== "/login") {
      window.location.href = "/login"
    }
  } else if (status === 403) {
    // Access may have changed: refresh permissions, then re-run route guards.
    void queryClient
      .invalidateQueries({ queryKey: ["currentUser"] })
      .then(() => router.invalidate())
  }
}
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Auth and permission errors won't change on retry; react immediately.
      retry: (failureCount, error) =>
        !(
          error instanceof AxiosError &&
          [401, 403].includes(error.response?.status ?? 0)
        ) && failureCount < 3,
    },
  },
  queryCache: new QueryCache({
    onError: handleApiError,
  }),
  mutationCache: new MutationCache({
    onError: handleApiError,
  }),
})

const router = createRouter({ routeTree, context: { queryClient } })
declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
        <Toaster richColors closeButton />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
