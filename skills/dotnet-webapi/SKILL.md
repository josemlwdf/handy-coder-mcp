---
name: dotnet-webapi
description: Build and modify ASP.NET Core Web API endpoints with correct HTTP semantics, OpenAPI metadata, validation, and error handling. Use for controllers, minimal APIs, DTOs, OpenAPI, endpoint tests, and global error handling.
tags: dotnet, aspnet-core, web-api, openapi, backend
---

# ASP.NET Core Web API

Build or modify ASP.NET Core HTTP APIs matching project style with correct HTTP status codes, documented contracts, safe errors, and verifiable tests.

## Related Tools & Environment

Handy Coder MCP exposes tools through a router:
1. Use `get_capabilities` if availability is unclear.
2. Use `get_capabilities` to find tools, then `get_tool_details` for schemas.
3. Call via `invoke_tool`.

- **Inspection**: `list_dir`, `find_files`, `search_text`, `read_files`, `code_intel`.
- **Build/Test**: `build_project`, `terminal_exec` for `dotnet build`, `dotnet test`, `dotnet run`, and HTTP checks. Do not use `run_tests` for .NET (use `dotnet-tests` skill workflow).
- **Diagnostics**: `code_get_diagnostics` (does not replace a .NET build).

## Related Skills

- `implement`: Feature implementation.
- `dotnet-tests`: Test selection and execution.
- `diagnosing-bugs`: Endpoint debugging.
- `analyzing-dotnet-performance`: Performance tuning.

## When to Use

- Add or modify controller or minimal API endpoints.
- Configure OpenAPI/Swagger and endpoint metadata.
- Define request/response DTOs and status-code behavior.
- Create `.http` request files for API testing.
- Configure global exception handling and exception-to-status mapping.

## When Not to Use

- General C# refactoring or non-API code.
- EF Core data modeling or query optimization (use project conventions, `implement`, or `diagnosing-bugs`).
- Frontend, Razor, or Blazor UI.
- gRPC services or SignalR hubs.

---

## Workflow

### Step 1: Detect API Style
Inspect project structure before coding:
1. Search for classes inheriting `ControllerBase` with `[ApiController]` or `app.MapGet`/`MapPost`/etc. in `Program.cs`.
2. Match existing style. **Never mix controllers and minimal APIs in the same project.**
3. Default to minimal APIs for new projects unless controllers are requested.

### Step 2: Define Request and Response Types
- **Isolate DTOs**: Never expose EF Core domain entities directly in request/response bodies.
- **DTO Rule**: Use immutable `sealed record` types (`sealed` improves JIT devirtualization CA1852).
- **Naming Conventions**:
  - Create input: `Create{Entity}Request`
  - Update input: `Update{Entity}Request`
  - Single output: `{Entity}Response`
  - List output: `{Entity}ListResponse`
- **XML Docs**: Add `<summary>` XML comments to every API DTO for automated OpenAPI documentation.
- **Date/Time**: Use `DateTimeOffset` instead of `DateTime` for ISO 8601 UTC offset preservation.
- **Enums**: Configure serialization as strings by default (`JsonStringEnumConverter`).
- **DTO Examples**:
  ```csharp
  /// <summary>Product returned by the API.</summary>
  public sealed record ProductResponse(
      int Id,
      string Name,
      decimal Price,
      Category Category,
      bool IsAvailable,
      DateTimeOffset CreatedAt);

  /// <summary>Payload for creating a product.</summary>
  public sealed record CreateProductRequest
  {
      [Required, MaxLength(200)]
      public required string Name { get; init; }

      [Range(0.01, 999999.99)]
      public required decimal Price { get; init; }

      public required Category Category { get; init; }
  }
  ```
- **Validation**: MVC controllers validate data annotations automatically. For .NET 10+ minimal APIs, register validation in `Program.cs`:
  ```csharp
  builder.Services.AddValidation();
  ```

### Step 3: Implement Endpoints
- **Minimal API Organization**: Group routes by resource in static classes with extension methods (`MapProducts(this WebApplication app)`).
- **Prefer `TypedResults`**: Exposes response types in signatures for rich OpenAPI metadata.
  - Multi-result handlers: Declare explicit return types like `Results<Ok<ProductResponse>, NotFound>`. Avoid bare ternaries with mixed types.
  - Complex handlers (7+ branches): `Results` factory returning `IResult` is acceptable.
- **HTTP Status Codes**:
  - GET single: `200 OK` (or `404 Not Found`)
  - GET list: `200 OK`
  - POST create: `201 Created` + `Location` header (`CreatedAtAction` or `TypedResults.Created`)
  - PUT/PATCH update: `200 OK` (or `404 Not Found`)
  - DELETE: `204 No Content` (or `404 Not Found`)
- **Cancellation**: Accept `CancellationToken` in every endpoint signature and forward through all async downstream calls.

### Step 4: Configure OpenAPI
- **.NET 9+**: Use built-in ASP.NET Core OpenAPI (`builder.Services.AddOpenApi()` and `app.MapOpenApi()`). **Do not add `Swashbuckle.*` packages to .NET 9+ projects.**
- **Metadata**: Enhance minimal APIs with `.WithName()`, `.WithSummary()`, `.WithDescription()`, and `.Produces<T>()`.
- **String Enums**: Register `JsonStringEnumConverter` in JSON options for Minimal APIs (`ConfigureHttpJsonOptions`) or Controllers (`AddJsonOptions`).

### Step 5: Configure Error Handling
- Use global exception handling returning RFC 7807 Problem Details.
- Register built-in exception middleware and custom `IExceptionHandler` in `Middleware/`:
  ```csharp
  builder.Services.AddExceptionHandler<ApiExceptionHandler>();
  builder.Services.AddProblemDetails();
  app.UseExceptionHandler();
  ```

### Step 6: Use a Service Layer
- Define an interface (`IProductService`) and a `sealed` implementation (`ProductService`).
- Register services via interface in DI (`builder.Services.AddScoped<IProductService, ProductService>()`).

### Step 7: Create `.http` Test File
- Place at project root with requests covering success and error paths for every endpoint, matching `launchSettings.json` ports.

### Step 8: Build and Verify
1. Build with `dotnet build` (`build_project` or `terminal_exec`).
2. Run .NET tests via `dotnet test` (following `dotnet-tests`).
3. Run HTTP checks (e.g. `curl`) to verify OpenAPI (`/openapi/v1.json`) and status codes.

---

## Validation Checklist

- [ ] Endpoints use correct HTTP status codes (POST = `201 Created` + `Location`, DELETE = `204 No Content`).
- [ ] Every endpoint and downstream async call accepts and forwards `CancellationToken`.
- [ ] OpenAPI document generates successfully with endpoint summary/description metadata and string enums.
- [ ] Errors return RFC 7807 Problem Details via global exception handler in `Middleware/`.
- [ ] DTOs are immutable `sealed record` types with XML `<summary>` docs and `DateTimeOffset` for dates.
- [ ] No domain entities leaked in API contracts; services use interface + DI registration.
- [ ] `.http` test file covers all new endpoints.
- [ ] `dotnet build` passes without errors or new warnings; relevant tests pass.

## Common Pitfalls & Correct Actions

| Pitfall | Correct Action |
|---|---|
| Exposing domain entities directly | Use separate `sealed record` request/response DTOs. |
| Omitting `CancellationToken` | Add to endpoint signatures and forward to all async calls. |
| Returning `200 OK` on POST creation | Return `201 Created` with `Location` header. |
| Mixing controller and minimal API styles | Stick to one consistent style per project. |
| Unsafe exception handling / leaking details | Use global `IExceptionHandler` with safe Problem Details messages. |
| Adding Swashbuckle to .NET 9+ | Use built-in `AddOpenApi()` instead. |
