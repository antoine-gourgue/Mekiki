/** Shows a failed engine call as an error toast. */
export function useErrorToast() {
  const toast = useToast()
  return (error: unknown, title = 'Opération impossible') =>
    toast.add({ title, description: engineErrorMessage(error), color: 'error' })
}
