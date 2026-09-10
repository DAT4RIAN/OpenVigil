declare module "parenthesis" {
    namespace parens {
        // One entry in the returned nested array
        type Node = string | ArrayTree;
        // A nested array of strings
        interface ArrayTree extends Array<Node> {}
        // Second-argument options used by the function
        interface Opts {
            // Single brackets string or list of strings to detect brackets. Can be repeating brackets eg. "" or ''.
            brackets?: string | string[],
            // Escape prefix for flat references.
            escape?: string,
            // `flat` is a boolean but since it affects return type, it's explicitly specified below
        }

        // Parse parentheses from a string, return folded arrays
        function parse(
            str: string,
            opts?: string | string[] | (parens.Opts & { flat?: false })
        ): parens.ArrayTree;
        // Parse parentheses from a string, return flat array
        function parse(
            str: string,
            opts: (parens.Opts & { flat: true })
        ): string[];

        // Stringify tokens back. Pass {flat: true} flag for flat tokens array.
        function stringify(tokens: ArrayTree, opts?: {flat: boolean}): string;
    }

    // Parse parentheses from a string, return folded arrays
    function parens(
        str: string,
        opts?: string | string[] | (parens.Opts & { flat?: false })
    ): parens.ArrayTree;
    // Parse parentheses from a string, return flat array
    function parens(
        str: string,
        opts: (parens.Opts & { flat: true })
    ): string[];
    function parens(tokens: parens.ArrayTree, opts?: {flat: boolean}): string;

    // imports via `import paren from "parenthesis", can call the export
    // directly or use `paren.parse` / `paren.stringify`.
    export = parens;
}
