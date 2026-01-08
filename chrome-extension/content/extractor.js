class DataExtractor {
    async extract(extractionSpec) {
        const { mode, fields, table_spec, type } = extractionSpec;

        // Default to 'simple' mode if not specified
        // Support 'type' as alias for mode for cleaner config
        const extractionMode = mode || type || (fields ? 'simple' : 'table');

        if (extractionMode === 'simple') {
            return this.extractSimple(fields);
        } else if (extractionMode === 'table') {
            return await this.extractTable(table_spec || extractionSpec); // Support nested or direct spec
        } else {
            throw new Error(`Unknown extraction mode: ${extractionMode}`);
        }
    }

    extractSimple(fields) {
        // ... existing simple extraction logic (unchanged) ...
        const data = {};

        for (const field of fields) {
            const { name, locator, attribute } = field;

            // console.log(`[Extractor] Attempting to find element with locator:`, locator);
            const element = new DOMActions().findElement(locator);

            if (!element) {
                // console.warn(`[Extractor] Element not found for field "${name}"`);
                data[name] = null;
                continue;
            }

            // Extract requested attribute
            switch (attribute) {
                case 'innerText':
                    data[name] = element.innerText.trim();
                    break;
                case 'innerHTML':
                    data[name] = element.innerHTML;
                    break;
                case 'value':
                    data[name] = element.value;
                    break;
                default:
                    data[name] = element.getAttribute(attribute);
            }
        }

        return { structured_data: data, metadata: { fields_extracted: fields.length } };
    }

    async extractTable(spec) {
        console.log('[Extractor] Starting table extraction:', spec);
        const { selector, schema, pagination } = spec;

        let allRows = [];
        let page = 1;
        const maxPages = pagination?.enabled ? (pagination.max_pages || 5) : 1;

        // Loop for pagination
        while (page <= maxPages) {
            // 1. Find table
            const table = document.querySelector(selector);
            if (!table) {
                console.warn(`[Extractor] Table not found with selector: ${selector} on page ${page}`);
                break;
            }

            // 2. Detect Headers & Map to Schema
            const headers = this.detectHeaders(table);
            const columnMapping = this.mapHeadersToSchema(headers, schema); // maps index -> schema key
            console.log(`[Extractor] Page ${page} headers:`, headers);
            console.log(`[Extractor] Page ${page} mapping:`, columnMapping);

            // 3. Extract Rows
            const rows = this.extractRows(table, columnMapping);
            console.log(`[Extractor] Page ${page} extracted ${rows.length} rows`);
            allRows = allRows.concat(rows);

            // 4. Handle Pagination
            if (pagination?.enabled) {
                const hasNext = await this.handlePagination(pagination);
                if (!hasNext) break;
                page++;
            } else {
                break;
            }
        }

        return {
            structured_data: allRows,
            metadata: {
                total_rows: allRows.length,
                pages_extracted: page,
                schema_keys: Object.keys(schema || {})
            }
        };
    }

    detectHeaders(table) {
        // Try standard <thead> <th>
        let headers = [];
        const thElements = table.querySelectorAll('thead th');
        if (thElements.length > 0) {
            headers = Array.from(thElements).map(th => th.innerText.trim());
        } else {
            // Fallback: first row <tr>
            const firstRow = table.querySelector('tr');
            if (firstRow) {
                headers = Array.from(firstRow.children).map(c => c.innerText.trim());
            }
        }
        return headers;
    }

    mapHeadersToSchema(headers, schema) {
        // Returns { columnIndex: schemaKey }
        const mapping = {};
        if (!schema) return {};

        headers.forEach((headerText, index) => {
            const normalizedHeader = headerText.toLowerCase();

            for (const [key, config] of Object.entries(schema)) {
                // Check key match
                if (key.toLowerCase() === normalizedHeader) {
                    mapping[index] = key;
                    break;
                }
                // Check synonyms
                if (config.synonyms && Array.isArray(config.synonyms)) {
                    if (config.synonyms.some(s => s.toLowerCase() === normalizedHeader)) {
                        mapping[index] = key;
                        break;
                    }
                }
            }
        });
        return mapping;
    }

    extractRows(table, columnMapping) {
        const results = [];
        // Skip header row if we detected one in standard places
        let rows = Array.from(table.querySelectorAll('tbody tr'));
        if (rows.length === 0) {
            // Fallback: all tr, skipping first if it looks like header
            rows = Array.from(table.querySelectorAll('tr'));
            if (table.querySelector('thead')) {
                // If there was a thead, we likely already skipped it, or querySelectorAll('tr') found it
                // Better safety: querySelectorAll('tr') includes thead rows if not scoped
                // simpler: just process all rows and filter empty or those that match headers exactly?
                // For now, assume good html structure or generic tr list
                // If thead exists, tbody tr is safest. If no tbody, assume implicit tbody or just trs.
            } else if (rows.length > 0) {
                // Heuristic: skip first row if we used it for headers
                rows.shift();
            }
        }

        for (const row of rows) {
            const cells = row.children;
            const rowData = {};
            let hasData = false;

            for (const [colIndex, schemaKey] of Object.entries(columnMapping)) {
                if (cells[colIndex]) {
                    rowData[schemaKey] = cells[colIndex].innerText.trim();
                    hasData = true;
                }
            }

            // Only add if we extracted something useful mapped to schema
            if (hasData) {
                results.push(rowData);
            }
        }
        return results;
    }

    async handlePagination(paginationSpec) {
        const { next_btn_selector } = paginationSpec;
        if (!next_btn_selector) return false;

        const nextBtn = document.querySelector(next_btn_selector);

        // Check if exists and looks active
        if (!nextBtn || nextBtn.disabled || nextBtn.classList.contains('disabled')) {
            console.log('[Extractor] Pagination: Next button not actionable');
            return false;
        }

        console.log('[Extractor] Pagination: Clicking next button');
        nextBtn.click();

        // Wait for update
        await new Promise(resolve => setTimeout(resolve, 2000)); // Simple wait for now, better to wait for network idle or DOM change
        return true;
    }
}
