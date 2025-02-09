// webpack.config.js
const path = require("path");
const HtmlWebpackPlugin = require("html-webpack-plugin");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");
const TerserPlugin = require("terser-webpack-plugin");
const CssMinimizerPlugin = require("css-minimizer-webpack-plugin");

module.exports = {
  mode: "production",
  entry: "./src/ide/www/webpackMain.js",
  output: {
    filename: "bundle.js",
    path: path.resolve(__dirname, "webpack"), // output folder
  },
  module: {
    rules: [
      {
        test: /\.css$/,
        use: [MiniCssExtractPlugin.loader, "css-loader"],
      },
      {
        test: /\.js$/,
        exclude: /node_modules/,
        //        use: ["babel-loader"], // Optional: only if you need Babel
      },
    ],
  },
  resolve: {
    alias: {
      "../../lib": path.resolve(__dirname, "src/ide/www/js/cm5"),
    },
    extensions: [".js", ".min.js"],
  },
  optimization: {
    minimize: true,
    minimizer: [new TerserPlugin(), new CssMinimizerPlugin()],
  },
  plugins: [
    new MiniCssExtractPlugin({ filename: "styles.css" }),
    new HtmlWebpackPlugin({
      template: "./src/ide/www/index.html",
      minify: {
        collapseWhitespace: true,
        removeComments: true,
      },
    }),
  ],
};
