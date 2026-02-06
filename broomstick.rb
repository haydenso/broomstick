class Broomstick < Formula
  include Language::Python::Virtualenv

  desc "Mole-inspired cleanup tool for Python environments and packages"
  homepage "https://github.com/haydenso/broomstick"
  url "https://github.com/haydenso/broomstick/archive/refs/tags/v2.0.0.tar.gz"
  sha256 "" # Will be filled after creating the release
  license "MIT"
  head "https://github.com/haydenso/broomstick.git", branch: "main"

  depends_on "python@3.11"

  def install
    virtualenv_install_with_resources
  end

  test do
    system "#{bin}/broomstick", "--help"
  end
end
