const path = require("path");
const HtmlWebpackPlugin = require("html-webpack-plugin");

module.exports = {
  mode: "development",
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
    ],
  },
  plugins: [
    new HtmlWebpackPlugin({
      template: "index.html", // Use your existing index.html as a template
      inject: "body", // Injects the bundle.js just before closing </body>
    }),
  ],
};
