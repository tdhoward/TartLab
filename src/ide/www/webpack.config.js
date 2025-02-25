const path = require("path");
const HtmlWebpackPlugin = require("html-webpack-plugin");

module.exports = (env, argv) => ({
  mode: argv.mode || "development",
  entry: "./js/main.js",
  output: {
    filename: "bundle.js",
    path: path.resolve(__dirname, "dist"),
    clean: true, // Cleans the output directory before each build (optional)
  },
  devServer: {
    static: "./dist",
  },
  module: {
    rules: [
      {
        test: /\.css$/,
        use: ["style-loader", "css-loader"],
      },
      {
        test: /\.svg$/,
        exclude: path.resolve(__dirname, "img/logo.svg"),
        type: "asset/inline",
        use: [
          {
            loader: "svgo-loader",
            options: {
              plugins: [
                { name: "removeTitle", active: true },
                { name: "removeComments", active: true },
                { name: "removeDesc", active: true },
              ],
            },
          },
        ],
      },
      // Rule for logo.svg to emit it as a separate file
      {
        test: /logo\.svg$/,
        type: "asset/resource",
        generator: {
          filename: "img/[name][ext]",
        },
      },
    ],
  },
  plugins: [
    new HtmlWebpackPlugin({
      template: "index.html", // Use your existing index.html as a template
      inject: "body", // Injects the bundle.js just before closing </body>
    }),
  ],
});
