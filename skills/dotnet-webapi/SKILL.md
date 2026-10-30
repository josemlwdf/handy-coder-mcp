---
name: dotnet-webapi
description: >-
  Builds and modifies ASP.NET Core Web API endpoints with correct HTTP
  semantics, OpenAPI metadata, and error handling. Use for controllers,
  minimal APIs, DTOs, OpenAPI/Swagger, .http tests, and global error handling.
  Not for general C# style, EF Core data/query optimization, frontend/Blazor,
  gRPC, or SignalR.
---

# ASP.NET Core Web API

Build or modify ASP.NET Core HTTP APIs. Match project style. Use correct HTTP status codes, documented contracts, safe errors, and verifiable tests.

## When to Use

- Add or modify controller or minimal API endpoints.
- Configure OpenAPI/Swagger and endpoint metadata.
- Define request/response DTOs and status-code behavior.
- Create `.http` request files for API testing.
- Configure global exception handling and exception-to-status mapping.

## When Not to Use

- General C# style or non-API refactoring.
- EF Core data modeling or query optimization; use relevant EF Core guidance.
- Frontend, Razor, or Blazor UI.
- gRPC services.
- SignalR hubs or real-time messaging.

## Inputs / Prerequisites

Inspect project context before changing code:

- ASP.NET Core entry point, usually `Program.cs`.
- Existing controllers (`ControllerBase`, `[ApiController]`).
- Existing minimal API routes (`app.MapGet`, `MapPost`, `MapPut`, `MapDelete`, etc.).
- Existing DTOs, models, validation, and error-handling types.
- Available build, run, and test commands.

New endpoint → inspect project structure first. Match existing conventions; do not mix API styles.

## Workflow

### Step 1: Detect API Style

Search project before coding:

1. Find classes inheriting `ControllerBase` or marked `[ApiController]`.
2. Find `app.MapGet`, `app.MapPost`, `app.MapPut`, `app.MapDelete`, etc. in `Program.cs` and endpoint files.
3. Existing controllers → use controllers.
4. Existing minimal APIs → use minimal APIs.
5. Neither (new project) → default to minimal APIs unless user requests controllers.

**Do not mix controllers and minimal APIs in one project.**

### Step 2: Define Request and Response Types

Create dedicated API input/output types. Never expose EF Core entities directly in request or response bodies.

**DTO rule: use `sealed record`.** Records provide immutability, value equality, concise syntax. `sealed` blocks unintended inheritance and supports JIT devirtualization (CA1852).

**Naming:**

| Role | Convention | Example |
|---|---|---|
| Create input | `Create{Entity}Request` | `CreateProductRequest` |
| Update input | `Update{Entity}Request` | `UpdateProductRequest` |
| Single output | `{Entity}Response` | `ProductResponse` |
| List output | `{Entity}ListResponse` | `ProductListResponse` |

**XML docs:** Add `<summary>` XML comments to every API-exposed request and response DTO. OpenAPI can include these comments automatically.

Reference: https://learn.microsoft.com/en-us/aspnet/core/fundamentals/openapi/openapi-comments

**Date/time:** Use `DateTimeOffset`, not `DateTime`, for DTO date/time properties. It preserves UTC offset, avoids ambiguous timezone conversion, and serializes as ISO 8601 with offset.

Reference: https://learn.microsoft.com/en-us/dotnet/api/system.datetimeoffset

**JSON compatibility:** Preserve existing serialization behavior by default. Do not silently add stricter serialization/deserialization settings to an existing API; case-sensitive matching or strict number handling can break clients.

For new projects, or explicit strict-JSON requests, consider:

```csharp
// Use only for new projects, existing matching configuration,
// or when user explicitly requests stricter JSON behavior.
builder.Services.ConfigureHttpJsonOptions(options =>
{
    // Reject numbers encoded as JSON strings.
    options.SerializerOptions.NumberHandling = JsonNumberHandling.Strict;
    // Require exact property-name casing during deserialization.
    options.SerializerOptions.PropertyNameCaseInsensitive = false;
    // Reject duplicate JSON property names during deserialization.
    options.SerializerOptions.AllowDuplicateProperties = false;
    // Omit null properties from serialized output.
    options.SerializerOptions.DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull;
});
```

**Enums:** Serialize enum values as strings by default. Use integer serialization only when user explicitly requests it. Configure `JsonStringEnumConverter` in Step 4.

**Response DTO:** Prefer positional sealed records:

```csharp
/// <summary>Product returned by the API.</summary>
public sealed record ProductResponse(
    int Id,
    string Name,
    decimal Price,
    Category Category,
    bool IsAvailable,
    DateTimeOffset CreatedAt);
```

**Request DTO:** Use sealed records with `init` properties; data annotations work naturally:

```csharp
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

Use same pattern for `Update{Entity}Request`; add required update fields, e.g. `IsAvailable`.

**Minimal API validation:** MVC controllers validate data annotations automatically. Minimal APIs need explicit validation registration. For .NET 10+ minimal API projects, add in `Program.cs`:

```csharp
builder.Services.AddValidation();
```

This adds an endpoint filter. It validates data-annotated parameters before handler execution and returns `400 Bad Request` with validation Problem Details on failure.

Reference: https://learn.microsoft.com/aspnet/core/fundamentals/minimal-apis?view=aspnetcore-10.0

**Do not use mutable DTO classes** with `{ get; set; }`. Use immutable `sealed record` types.

### Step 3: Implement Endpoints

Apply HTTP conventions consistently to controllers and minimal APIs.

#### Organize Minimal API Endpoints

Group routes by resource using static classes and static `Map<Resource>` methods:

1. One static class per resource, e.g. `ProductEndpoints`, `CategoryEndpoints`.
2. Add static extension method `Map<Resource>(this WebApplication app)`.
3. Register that resource's `MapGet`, `MapPost`, `MapPut`, `MapDelete`, etc. inside the method.
4. Call each resource's `Map` method from `Program.cs`.

This keeps resource routes grouped and code navigable as API grows.

#### Prefer `TypedResults`

Prefer `TypedResults` over `Results`. `TypedResults` exposes response types in handler signatures and gives OpenAPI richer metadata automatically.

Handler returns multiple result types (e.g. `Ok` or `NotFound`) → declare explicit `Results<T1, T2>` return type:

```csharp
async Task<Results<Ok<ProductResponse>, NotFound>> (int id, ...) => ...
```

**Do not put different `TypedResults` types in a bare ternary without explicit return type.** `Ok<T>` and `NotFound` have no common inferred type. Compiler may fall back to `RequestDelegate(HttpContext)`, causing `CS1593: Delegate 'RequestDelegate' does not take N arguments`.

**Fallback:** Handler has many conditional branches (7+ result types) → `Results` factory is acceptable (`Results.Ok()`, `Results.NotFound()`). It returns `IResult`; simpler signature, less compile-time OpenAPI inference.

#### HTTP Status Codes

| Operation | Success | Common errors |
|---|---|---|
| GET single | `200 OK` | `404 Not Found` |
| GET list | `200 OK` | — |
| POST create | `201 Created` + `Location` header | `400 Bad Request`, `409 Conflict` |
| PUT full update | `200 OK` | `400 Bad Request`, `404 Not Found` |
| PATCH partial/action | `200 OK` | `400 Bad Request`, `404 Not Found` |
| DELETE | `204 No Content` | `404 Not Found`, `409 Conflict` |

**POST create:** Always return `201 Created` with `Location` pointing to new resource.

- Controller: `CreatedAtAction(nameof(GetById), new { id = ... }, response)`.
- Minimal API: `TypedResults.Created($"/api/products/{id}", response)`.

**CancellationToken:** Add `CancellationToken` to every endpoint signature. Forward it through every async call: service methods, EF Core queries, `HttpClient`, etc. Client disconnect → server can cancel remaining work.

```csharp
// Controller
[HttpGet("{id}")]
public async Task<ActionResult<ProductResponse>> GetById(
    int id, CancellationToken cancellationToken)
{
    var product = await _productService.GetByIdAsync(id, cancellationToken);
    return product is null ? NotFound() : Ok(product);
}

// Minimal API: TypedResults + explicit return type
app.MapGet("/api/products/{id}", async Task<Results<Ok<ProductResponse>, NotFound>> (
    int id, IProductService service, CancellationToken cancellationToken) =>
{
    var product = await service.GetByIdAsync(id, cancellationToken);
    return product is null ? TypedResults.NotFound() : TypedResults.Ok(product);
});
```

### Step 4: Configure OpenAPI

Every Web API needs OpenAPI documentation. Check existing configuration before adding anything.

**.NET 9+:** Prefer built-in ASP.NET Core OpenAPI:

```csharp
builder.Services.AddOpenApi();
app.MapOpenApi(); // usually expose in development
```

No extra package needed.

**Do not add `Swashbuckle.*` NuGet packages to .NET 9+ projects.** This includes `Swashbuckle.AspNetCore`, `Swashbuckle.AspNetCore.SwaggerUI`, and `Swashbuckle.AspNetCore.SwaggerGen`. Swashbuckle has known compatibility issues with .NET 9+ and .NET 10 OpenAPI types.

For .NET 8 or earlier, Swashbuckle is acceptable. Existing Swashbuckle installation → keep it unless user asks for removal.

Reference: https://learn.microsoft.com/en-us/aspnet/core/fundamentals/openapi/overview

#### Add Endpoint Metadata

Document endpoints with meaningful metadata, not route names alone. For minimal APIs:

```csharp
app.MapGet("/api/products/{id}", handler)
    .WithName("GetProductById")
    .WithSummary("Get a product by ID")
    .WithDescription("Returns full product details, including category.")
    .Produces<ProductResponse>(StatusCodes.Status200OK)
    .Produces(StatusCodes.Status404NotFound);
```

#### Serialize Enums as Strings

Configure JSON so enum values appear as readable strings in responses and OpenAPI schemas. Do this by default unless user explicitly requests integer serialization.

Minimal APIs:

```csharp
builder.Services.ConfigureHttpJsonOptions(options =>
    options.SerializerOptions.Converters.Add(new JsonStringEnumConverter()));
```

Controllers / MVC:

```csharp
builder.Services.AddControllers()
    .AddJsonOptions(options =>
    {
        options.JsonSerializerOptions.Converters.Add(new JsonStringEnumConverter());
    });
```

Configure the option type matching the API style. Minimal APIs and MVC use different JSON options.

### Step 5: Configure Error Handling

Use global exception handling. Avoid endpoint-level try/catch blocks for routine API error mapping. Return RFC 7807 Problem Details for error responses.

**.NET 8+:** Prefer built-in exception middleware:

```csharp
builder.Services.AddProblemDetails();

app.UseExceptionHandler();
app.UseStatusCodePages();
```

Need custom exception-to-status mapping (e.g. `NotFoundException` → 404) → implement `IExceptionHandler`:

```csharp
internal sealed class ApiExceptionHandler(ILogger<ApiExceptionHandler> logger)
    : IExceptionHandler
{
    public async ValueTask<bool> TryHandleAsync(
        HttpContext httpContext,
        Exception exception,
        CancellationToken cancellationToken)
    {
        var (statusCode, title) = exception switch
        {
            KeyNotFoundException => (StatusCodes.Status404NotFound, "Not Found"),
            ArgumentException => (StatusCodes.Status400BadRequest, "Bad Request"),
            InvalidOperationException => (StatusCodes.Status409Conflict, "Conflict"),
            _ => (0, (string?)null)
        };

        if (statusCode == 0)
            return false; // Let default handler process it.

        // Returning true suppresses exception diagnostics middleware for this exception.
        // Log/telemetry must happen before returning.
        logger.LogWarning(exception, "Handled API exception: {Title}", title);

        httpContext.Response.StatusCode = statusCode;
        await httpContext.Response.WriteAsJsonAsync(new ProblemDetails
        {
            Status = statusCode,
            Title = title,
            // Never expose exception.Message; may leak internal details.
            // Use safe, user-facing text.
            Detail = title,
            Instance = httpContext.Request.Path
        }, cancellationToken);

        return true;
    }
}
```

Register handler:

```csharp
builder.Services.AddExceptionHandler<ApiExceptionHandler>();
builder.Services.AddProblemDetails();

app.UseExceptionHandler();
```

**File placement:** Put exception handler classes in `Middleware/`. Never place them at project root.

### Step 6: Use a Service Layer

Do not inject data stores directly into controllers or endpoint handlers. Put data access and entity-to-DTO mapping in a service.

For every service, define an interface and a `sealed` implementation. Interface enables mock-based unit tests and follows Dependency Inversion Principle.

```csharp
// Services/IProductService.cs
public interface IProductService
{
    Task<IReadOnlyList<ProductResponse>> GetAllAsync(CancellationToken ct);
    Task<ProductResponse?> GetByIdAsync(int id, CancellationToken ct);
    Task<ProductResponse> CreateAsync(CreateProductRequest request, CancellationToken ct);
}

// Services/ProductService.cs
public sealed class ProductService(...) : IProductService
{
    // Data access and entity-to-DTO mapping.
}
```

Register interface, not concrete implementation:

```csharp
// Program.cs
builder.Services.AddScoped<IProductService, ProductService>();
```

For EF Core migrations, Fluent API, `AsNoTracking`, seed data, and data-access patterns, follow the project's EF Core guidance.

### Step 7: Create `.http` Test File

After adding endpoints, create a `.http` file at project root. Include a request for every new endpoint. File acts as living docs and manual test harness.

```http
@baseUrl = http://localhost:5000

### Get all products
GET {{baseUrl}}/api/products

### Get product by ID
GET {{baseUrl}}/api/products/1

### Create a product
POST {{baseUrl}}/api/products
Content-Type: application/json

{
  "name": "Wireless Mouse",
  "price": 29.99,
  "category": "Electronics"
}

### Delete a product
DELETE {{baseUrl}}/api/products/1
```

Rules:

- At least one realistic request per endpoint.
- Include error paths, e.g. nonexistent IDs.
- Match port to `launchSettings.json`.

### Step 8: Build and Verify

1. Run `dotnet build`; require zero errors and zero warnings.
2. Start app; verify OpenAPI document loads. Default route: `/openapi/v1.json`.
3. Run `.http` requests; verify actual status codes.

## Validation

Before completion, check every item:

- [ ] All endpoints use correct HTTP status codes (Step 3 table).
- [ ] POST returns `201 Created` and `Location` header.
- [ ] DELETE returns `204 No Content`.
- [ ] Every endpoint signature accepts `CancellationToken`.
- [ ] Every downstream async call receives the token.
- [ ] OpenAPI document generates and includes all new endpoints.
- [ ] Endpoints have useful summary/description metadata.
- [ ] Enums serialize as strings in JSON and OpenAPI unless integer format explicitly requested.
- [ ] Errors use RFC 7807 Problem Details.
- [ ] API request/response bodies expose no domain entities.
- [ ] Every API DTO has `<summary>` XML documentation.
- [ ] Date/time DTO properties use `DateTimeOffset`, not `DateTime`.
- [ ] `.http` file covers every new endpoint.
- [ ] `dotnet build` passes with zero errors and warnings.
- [ ] Every DTO is a `sealed record`, not mutable class.
- [ ] Minimal API handlers use `TypedResults` and explicit `Results<T1, T2>` when returning multiple result types.
- [ ] Every service has an interface and DI registration through that interface.
- [ ] Exception handlers live in `Middleware/`.

## Common Pitfalls

| Pitfall | Correct action |
|---|---|
| Expose domain entities as API responses | Use separate `sealed record` request/response DTOs. Entities may leak navigation properties and internal fields. |
| Omit `CancellationToken` | Add it to every endpoint; forward through full async call chain. |
| Return `200 OK` after POST create | Return `201 Created` + `Location`. |
| Omit OpenAPI metadata | Add `.WithName()`, `.WithSummary()`, `.WithDescription()`, and `.Produces<T>()` where applicable. |
| Inject data stores into endpoint handlers | Use service layer and interface. |
| Mix controller and minimal API styles | Pick one style per project. Stay consistent. |
| Use `TypedResults` ternary without explicit return type | `Ok<T>` and `NotFound` differ. Declare `Task<Results<Ok<T>, NotFound>>` or use `Results` factory for complex branches. |
| Use mutable DTO classes | Use `sealed record`; positional properties for responses, `init` properties for requests. |
| Register service without interface | Define `IService`; register `AddScoped<IService, Service>()`. |
| Add Swashbuckle package to new .NET 9+ project | Use built-in `AddOpenApi()` + `MapOpenApi()`. Do not add any `Swashbuckle.*` package. |
| Omit DTO XML docs | Add `<summary>` to each request and response type; comments flow into OpenAPI. |
| Use `DateTime` for API date/time | Use `DateTimeOffset`; preserves offset and avoids timezone ambiguity. |
| Serialize enums as integers | Add `JsonStringEnumConverter`; strings are default unless user requests integers. |

## More Info

- [ASP.NET Core Web API overview](https://learn.microsoft.com/en-us/aspnet/core/web-api/) — Web API fundamentals.
- [OpenAPI in ASP.NET Core](https://learn.microsoft.com/en-us/aspnet/core/fundamentals/openapi/overview) — built-in OpenAPI, .NET 9+.
- [OpenAPI from XML comments](https://learn.microsoft.com/en-us/aspnet/core/fundamentals/openapi/openapi-comments) — XML docs in generated OpenAPI.
- [Minimal APIs overview](https://learn.microsoft.com/en-us/aspnet/core/fundamentals/minimal-apis/overview) — routing, binding, result types.
- [Handle errors in ASP.NET Core APIs](https://learn.microsoft.com/en-us/aspnet/core/web-api/handle-errors) — Problem Details and exception handling.
- [DateTimeOffset](https://learn.microsoft.com/en-us/dotnet/api/system.datetimeoffset) — preferred API date/time type.
