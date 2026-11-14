import {
  type QueryClient,
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"
import { redirect, useNavigate } from "@tanstack/react-router"
import { AxiosError } from "axios"
import { toast } from "sonner"

import {
  type Body_login_login_access_token as AccessToken,
  LoginService,
  type Permission,
  type UserPublic,
  type UserRegister,
  UsersService,
} from "@/client"
import { handleError } from "@/utils"
import useCustomToast from "./useCustomToast"

const isLoggedIn = () => {
  return localStorage.getItem("access_token") !== null
}

const currentUserQueryOptions = () =>
  queryOptions({
    queryKey: ["currentUser"],
    queryFn: async () => (await UsersService.readUserMe()).data,
  })

// Permissions come from the backend (`/users/me`), so the UI follows the
// same access rules that the API enforces.
const hasPermission = (
  user: UserPublic | null | undefined,
  permission: Permission,
) => Boolean(user?.permissions.includes(permission))

/**
 * Load the current user for a route guard. `fresh` always asks the backend,
 * so role or active-status changes are picked up on direct navigation.
 * A 401 (expired session, deactivated or deleted user) redirects to login.
 */
const loadCurrentUser = async (queryClient: QueryClient, fresh = false) => {
  try {
    return fresh
      ? await queryClient.fetchQuery({
          ...currentUserQueryOptions(),
          staleTime: 0,
        })
      : await queryClient.ensureQueryData(currentUserQueryOptions())
  } catch (error) {
    if (error instanceof AxiosError && error.response?.status === 401) {
      localStorage.removeItem("access_token")
      queryClient.clear()
      throw redirect({ to: "/login" })
    }
    throw error
  }
}

const requirePermission = async (
  queryClient: QueryClient,
  permission: Permission,
  preload = false,
) => {
  const user = await loadCurrentUser(queryClient, true)
  if (!hasPermission(user, permission)) {
    if (!preload) {
      toast.error("Access denied", {
        description: "You don't have permission to view that page.",
      })
    }
    throw redirect({ to: "/" })
  }
}

const useAuth = () => {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()

  const { data: user } = useQuery({
    ...currentUserQueryOptions(),
    enabled: isLoggedIn(),
  })

  const signUpMutation = useMutation({
    mutationFn: (data: UserRegister) =>
      UsersService.registerUser({ body: data }),
    onSuccess: () => {
      navigate({ to: "/login" })
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
  })

  const login = async (data: AccessToken) => {
    const response = await LoginService.loginAccessToken({
      body: data,
    })
    // Drop any data cached for a previously signed-in account.
    queryClient.clear()
    localStorage.setItem("access_token", response.data.access_token)
  }

  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: () => {
      navigate({ to: "/" })
    },
    onError: handleError.bind(showErrorToast),
  })

  const logout = () => {
    localStorage.removeItem("access_token")
    queryClient.clear()
    navigate({ to: "/login" })
  }

  return {
    signUpMutation,
    loginMutation,
    logout,
    user,
    can: (permission: Permission) => hasPermission(user, permission),
  }
}

export { isLoggedIn, loadCurrentUser, requirePermission }
export default useAuth
