class DataExtractor {
    extract(extractionSpec) {
        const { mode, fields, table_spec } = extractionSpec;

        if (mode === 'simple') {
            return this.extractSimple(fields);
        } else if (mode === 'table') {
            return this.extractTable(table_spec);
        } else {
            throw new Error(`Unknown extraction mode: ${mode}`);
        }
    }

    extractSimple(fields) {
        const data = {};

        for (const field of fields) {
            const { name, locator, attribute } = field;

            const element = new DOMActions().findElement(locator);

            if (!element) {
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
                    // Custom attribute
                    data[name] = element.getAttribute(attribute);
            }
        }

        return { structured_data: data, metadata: { fields_extracted: fields.length } };
    }

    extractTable(tableSpec) {
        const { row_locator, columns } = tableSpec;

        const rows = document.querySelectorAll(row_locator.value);
        const data = [];

        for (const row of rows) {
            const rowData = {};

            for (const column of columns) {
                const { column_name, cell_locator, attribute } = column;

                // Find cell within this row
                const cell = row.querySelector(cell_locator.value);

                if (cell) {
                    rowData[column_name] = attribute === 'innerText'
                        ? cell.innerText.trim()
                        : cell.getAttribute(attribute);
                } else {
                    rowData[column_name] = null;
                }
            }

            data.push(rowData);
        }

        return {
            structured_data: data,
            metadata: {
                rows_extracted: data.length,
                columns: columns.length
            }
        };
    }
}
