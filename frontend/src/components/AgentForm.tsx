export interface AgentFormValues {
  vapi_assistant_id: string;
  name: string;
  objective: string;
  description: string;
}

export function AgentForm({
  values,
  onChange,
  onSubmit,
  isPending,
  errorMessage,
}: Readonly<{
  values: AgentFormValues;
  onChange: (values: AgentFormValues) => void;
  onSubmit: () => void;
  isPending: boolean;
  errorMessage: string | null;
}>) {
  function field(key: keyof AgentFormValues) {
    return {
      value: values[key],
      onChange: (event: { target: { value: string } }) =>
        onChange({ ...values, [key]: event.target.value }),
    };
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
      className="space-y-4"
    >
      <div>
        <label htmlFor="vapi_assistant_id" className="block text-sm font-medium">
          Vapi assistant ID
        </label>
        <input
          id="vapi_assistant_id"
          className="mt-1 w-full rounded border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          {...field("vapi_assistant_id")}
        />
      </div>
      <div>
        <label htmlFor="name" className="block text-sm font-medium">
          Name
        </label>
        <input
          id="name"
          className="mt-1 w-full rounded border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          {...field("name")}
        />
      </div>
      <div>
        <label htmlFor="objective" className="block text-sm font-medium">
          Objective
        </label>
        <input
          id="objective"
          className="mt-1 w-full rounded border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          {...field("objective")}
        />
      </div>
      <div>
        <label htmlFor="description" className="block text-sm font-medium">
          Description
        </label>
        <textarea
          id="description"
          className="mt-1 w-full rounded border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          {...field("description")}
        />
      </div>
      {errorMessage !== null && (
        <p role="alert" className="text-sm text-red-600">
          {errorMessage}
        </p>
      )}
      <button
        type="submit"
        disabled={isPending}
        className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
      >
        {isPending ? "Saving…" : "Save agent"}
      </button>
    </form>
  );
}
