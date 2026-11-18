```{=html}
<div class="table-responsive">
<table class="quarto-listing-table table table-striped">
<thead>
<tr><th>Container</th><th>Registries</th><th>Platforms</th><th>Dockerfile</th></tr>
</thead>
<tbody class="list">
<% for (const item of items) { %>
<tr <%= metadataAttrs(item) %>>
<td>
<% if (item.readme) { %>
<a class="listing-title" href="<%- item.readme %>"><%- item.title %></a>
<% } else { %>
<span class="listing-title"><%- item.title %></span>
<% } %>
</td>
```

<td class="listing-registries"><%= item.registries %></td>
<td class="listing-platforms"><%= item.platforms %></td>
<td class="listing-source"><%= item.source %></td>

```{=html}
</tr>
<% } %>
</tbody>
</table>
</div>
```
